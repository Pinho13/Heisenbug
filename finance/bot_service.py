from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from typing import Optional, Dict, List
import threading
import time
import logging
import random
from django.db import transaction
from django.utils import timezone
from .uphold_api import UpholdAPIHandler
from .trading_engine import PortfolioOptimizer, TradeDecision
from .cache import MarketDataCache
from .models import TradeHistory, BotConfig, TradingPair, PriceSnapshot, UserBalance, AssetPool
logger = logging.getLogger(__name__)




class TradeBot:
    def __init__(self):
        from .uphold_api import UpholdAPIHandler
        self.api = UpholdAPIHandler()
        self.optimizer = PortfolioOptimizer(self.api)
        self.logger = logger

    def run_iteration(self):
        config = BotConfig.get_config()
        if not config.is_active: return []

        pairs = list(TradingPair.objects.filter(is_enabled=True).values_list('pair_symbol', flat=True))
        # Simulamos tickers a partir dos snapshots mais recentes
        tickers = {}
        for p in pairs:
            latest = PriceSnapshot.objects.filter(pair=p).order_by('-timestamp').first()
            if latest:
                tickers[p] = {'ask': latest.ask, 'bid': latest.bid}

        executed = []
        user_ids = UserBalance.objects.values_list('user_id', flat=True).distinct()

        for u_id in user_ids:
            balances = UserBalance.objects.filter(user_id=u_id)
            
            class Portfolio:
                def __init__(self, b): self.data = {i.currency: i.amount for i in b}
                def get_all_holdings(self): return self.data

            decision = self.optimizer.find_best_trade(Portfolio(balances), pairs, tickers, config.risk_tolerance, config.min_confidence_score)

            if decision:
                if self.execute_trade_by_id(decision, u_id):
                    executed.append(decision)
        return executed

    def execute_trade_by_id(self, decision, user_id):
        try:
            with transaction.atomic():
                # Tenta API, se der 404 ou erro, simulamos para fins de hackathon
                try:
                    self.api.place_order(f"{decision.from_pair}-{decision.to_pair}", decision.amount, "buy")
                except:
                    logger.warning("API Offline/404 - Seguindo com execução local")

                bal_from = UserBalance.objects.select_for_update().get(user_id=user_id, currency=decision.from_pair)
                bal_to, _ = UserBalance.objects.select_for_update().get_or_create(user_id=user_id, currency=decision.to_pair)

                # Cálculo: (Quantidade * Preço Origem) / Preço Destino
                bought_amount = (decision.amount * decision.from_price) / decision.to_price
                
                bal_from.amount -= decision.amount
                bal_to.amount += bought_amount
                
                bal_from.save()
                bal_to.save()
                if bal_from.amount <= 0: bal_from.delete()

                TradeHistory.objects.create(
                    user_id=user_id, pair=f"{decision.from_pair}-{decision.to_pair}",
                    operation="BUY", amount=decision.amount, price_at_execution=decision.to_price,
                    status="EXECUTED", confidence_score=decision.confidence
                )
                print(f"✅ Trade Executada para User {user_id}: {decision.from_pair} -> {decision.to_pair}")
                return True
        except Exception as e:
            print(f"❌ Erro no Bot: {e}")
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
