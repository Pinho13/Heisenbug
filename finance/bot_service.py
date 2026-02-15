from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from typing import Optional, Dict, List
import threading
import time
import logging
import random

from django.utils import timezone
from .uphold_api import UpholdAPIHandler
from .trading_engine import PortfolioOptimizer, TradeDecision
from .cache import MarketDataCache
from .models import TradeHistory, BotConfig, TradingPair, PriceSnapshot, UserBalance, AssetPool
logger = logging.getLogger(__name__)




class TradeBot:
    """
    Trade bot:
    - Analyze possible trades
    - Analyze risk
    - Execute if below risk threshold
    - Log decision
    """

    def __init__(self):
        self.api = UpholdAPIHandler()
        self.optimizer = PortfolioOptimizer(self.api)
        self.cache = MarketDataCache()
        self.logger = logger

    def fetch_market_data(self, pairs: List[str], ttl_seconds: int = 3) -> Dict[str, dict]:
        result = {}
        to_fetch = []

        for pair in pairs:
            cached = self.cache.get_price(pair, ttl_seconds)
            if cached:
                result[pair] = cached
            else:
                to_fetch.append(pair)

        if to_fetch:
            fresh_data = self.api.get_tickers_batch(to_fetch)
            for pair, ticker in fresh_data.items():
                currency = ticker.get('currency')
                if currency:
                    self.cache.set_price(pair, ticker, ttl_seconds)
                    result[pair] = ticker
                    self._store_price_snapshot(pair, currency, ticker)
        return result

    def execute_trade(self, decision: TradeDecision, config: BotConfig, user) -> bool: # Adicionado 'user' aqui
        try:
            self.logger.info(f"Executing trade for {user.username}: {decision.from_pair}->{decision.to_pair}")
            
            # Simulação de ordem na API
            result = self.api.place_order(decision.to_pair, decision.amount, "buy")
            
            if result:
                # A. Retirar saldo da moeda de origem
                bal_from = UserBalance.objects.get(user=user, currency=decision.from_pair)
                bal_from.amount -= Decimal(str(decision.amount))
                bal_from.save()

                # B. Adicionar saldo na moeda de destino
                bal_to, created = UserBalance.objects.get_or_create(
                    user=user,
                    currency=decision.to_pair,
                    defaults={'amount': Decimal('0')}
                )
                
                bought_amount = (Decimal(str(decision.amount)) * decision.from_price) / decision.to_price
                bal_to.amount += bought_amount
                bal_to.save()

            # Histórico
            TradeHistory.objects.create(
                user=user, # Adicionado o user ao histórico também!
                pair=f"{decision.from_pair}-{decision.to_pair}",
                operation="BUY",
                amount=decision.amount,
                price_at_execution=decision.to_price,
                status="EXECUTED" if result else "FAILED",
                confidence_score=decision.confidence,
                reason=decision.reason
            )

            return result is not None
        except Exception as e:
            self.logger.error(f"Failed to execute trade for {user.username}: {e}")
            return False

    def run_iteration(self) -> List[TradeDecision]:
        executed_trades = []
        try:
            config = BotConfig.get_config()
            if not config.is_active:
                return []

            # 1. Carregar preços
            enabled_pairs = list(TradingPair.objects.filter(is_enabled=True).values_list('pair_symbol', flat=True))
            tickers = self.fetch_market_data(enabled_pairs, ttl_seconds=config.cache_ttl_seconds)
            
            if not tickers:
                return []

            # --- SMART ORDER ROUTING ---
            from .utils import get_best_market_prices
            for pair in enabled_pairs:
                best = get_best_market_prices(pair)
                if best.get('buy') and pair in tickers:
                    tickers[pair]['ask'] = float(best['buy'])
                    tickers[pair]['bid'] = float(best['sell'])

            # 2. Iterar pelos IDs únicos na tua tabela UserBalance
            # Isto ignora se o User é do Django ou Custom, foca apenas no ID da FK
            user_ids = UserBalance.objects.values_list('user_id', flat=True).distinct()
            
            for u_id in user_ids:
                # Buscar saldos e moedas permitidas via ID puro
                user_balances = UserBalance.objects.filter(user_id=u_id)
                allowed_symbols = list(AssetPool.objects.filter(user_id=u_id, is_active=True).values_list('symbol', flat=True))
                
                if not user_balances.exists() or not allowed_symbols:
                    continue
                
                # Wrapper para o Optimizer
                class PortfolioWrapper:
                    def __init__(self, balances):
                        self.data = {b.currency: b.amount for b in balances}
                    def get_all_holdings(self):
                        return self.data

                portfolio = PortfolioWrapper(user_balances)

                # 3. Optimizer
                decision = self.optimizer.find_best_trade(
                    portfolio=portfolio,
                    available_pairs=enabled_pairs,
                    tickers=tickers,
                    risk_tolerance=config.risk_tolerance,
                    min_confidence=config.min_confidence_score,
                    trade_size_amount=config.trade_size_amount,
                    trade_size_percent=config.trade_size_percentage
                )

                if decision:
                    # Passamos o u_id em vez do objeto user
                    # Vamos precisar de um pequeno ajuste no execute_trade para aceitar o ID
                    success = self.execute_trade_by_id(decision, config, u_id)
                    if success:
                        executed_trades.append(decision)

            return executed_trades
        except Exception as e:
            self.logger.error(f"Erro na iteração: {e}")
            return []
    
    def execute_trade_by_id(self, decision, config, user_id):
            # Versão do execute_trade que usa apenas o ID para atualizar a DB
        try:
                # Simulação API
            result = self.api.place_order(decision.to_pair, decision.amount, "buy")
            if result:
                # Atualizar saldos via ID
                bal_from = UserBalance.objects.get(user_id=user_id, currency=decision.from_pair)
                bal_from.amount -= Decimal(str(decision.amount))
                bal_from.save()

                bal_to, _ = UserBalance.objects.get_or_create(user_id=user_id, currency=decision.to_pair)
                bal_to.amount += (Decimal(str(decision.amount)) * decision.from_price) / decision.to_price
                bal_to.save()
                return True
        except:
            return False

    def refresh_all_tickers(self) -> None:
        try:
            tickers = self.api.get_all_tickers()
            if not tickers:
                self.logger.warning("Full ticker refresh returned no data")
                return
            for ticker in tickers:
                pair = ticker.get('pair')
                currency = ticker.get('currency')
                if pair and currency:
                    self._store_price_snapshot(pair, currency, ticker)
            self.logger.debug(
                f"Refreshed {len(tickers)} ticker snapshots"
            )
            print("the tickers should be in the database now!")

        except Exception as e:
            self.logger.warning(
                f"Failed full ticker refresh: {e}",
                exc_info=True
            )

    def _store_price_snapshot(self, pair: str, currency: str, ticker: dict):
        """
        Guarda o preço real e simula variações de mercado
        """
        try:
            ask_base = Decimal(str(ticker.get('ask', 0)))
            bid_base = Decimal(str(ticker.get('bid', 0)))
            
            PriceSnapshot.objects.create(pair=pair, bid=bid_base, ask=ask_base, currency=currency)

            if random.random() > 0.5:
                variacao = ask_base * Decimal('0.01')
                
                PriceSnapshot.objects.create(pair=pair, bid=bid_base, ask=ask_base - (variacao * 2), currency=currency)
                PriceSnapshot.objects.create(pair=pair, bid=bid_base + (variacao * 2), ask=ask_base, currency=currency)
                self.logger.info(f"Oportunidade gerada para {pair}!")
            else:
                PriceSnapshot.objects.create(pair=pair, bid=bid_base, ask=ask_base, currency=currency)
                PriceSnapshot.objects.create(pair=pair, bid=bid_base, ask=ask_base, currency=currency)
                self.logger.info(f"Mercado estável para {pair}.")

        except Exception as e:
            self.logger.warning(f"Erro ao gravar snapshots para {pair}: {e}")


class BotRunner:
    """Manages bot execution loop."""

    def __init__(self):
        self.bot = TradeBot()
        self.running = False
        self.thread = None
        self.logger = logger
        # threads!
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.refreshed_future = None

    def start(self):
        if self.running:
            self.logger.warning("Bot is already running")
            return

        self.running = True
        self._run_loop()
        self.thread = threading.Thread(target=self._run_loop, daemon=False)
        self.thread.start()
        self.logger.info("Bot started")

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=10)
        self.logger.info("Bot stopped")

    def _run_loop(self):
        print("this is the side thread?")
        thresholdSeconds = 15.0
        lastFullPull = time.monotonic()
        try:
            from finance.models import BotConfig
            config = BotConfig.get_config()
            config.is_active = True
            print(config)
            while (True):
                now = time.monotonic()
                if now - lastFullPull >= thresholdSeconds:
                    print("trying to fetch tickers")
                    self.bot.refresh_all_tickers()
                    lastFullPull = now
                    time.sleep(config.check_interval_seconds)
                    self.bot.run_iteration()
        except Exception as e:
            self.logger.error(
                f"Error in bot loop: {e}",
                exc_info=True
            )
            time.sleep(5)

    def is_running(self) -> bool:
        return self.running and self.thread and self.thread.is_alive()
