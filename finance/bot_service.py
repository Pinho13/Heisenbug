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
from .trading_engine import PortfolioOptimizer
from .risk_analyzer import TradeDecision
from .cache import MarketDataCache
from .models import TradeHistory, BotConfig, TradingPair, PriceSnapshot, UserBalance, AssetPool
logger = logging.getLogger(__name__)

class TradeBot:
    def __init__(self, user_id=None):
        from .uphold_api import UpholdAPIHandler
        self.api = UpholdAPIHandler()
        # Get user_id from config if not provided, else use the one passed
        if user_id is None:
            try:
                config = BotConfig.get_config()
                if config.bot_user:
                    user_id = config.bot_user.id
                else:
                    user_id = 1
            except:
                user_id = 1
        self.user_id = user_id 

    def run_iteration(self):
        config = BotConfig.get_config()
        if not config.is_active: return []

        # Get all available price snapshots dynamically
        recent_snapshots = PriceSnapshot.objects.values('pair').distinct()
        
        tickers = {}
        for snap in recent_snapshots:
            pair = snap['pair']
            s = PriceSnapshot.objects.filter(pair=pair).order_by('-timestamp').first()
            if s: tickers[pair] = {'ask': s.ask, 'bid': s.bid}

        balances = {b.currency: b.amount for b in UserBalance.objects.filter(user_id=self.user_id)}
        
        # Look for sell opportunities first (take profits on winning BUY positions)
        executed = []
        buy_trades = TradeHistory.objects.filter(user_id=self.user_id, status="EXECUTED", operation="BUY").order_by('-timestamp')[:50]
        
        for trade in buy_trades:
            # Check if we should sell this position for profit
            pair_parts = trade.pair.split('-')
            if len(pair_parts) != 2: continue
            
            # We bought the second currency (pair_parts[1]), check if we can sell it at profit
            currency_bought = pair_parts[1]
            if currency_bought not in balances or balances[currency_bought] <= 0:
                continue
                
            current_ticker = tickers.get(trade.pair)
            if current_ticker and float(current_ticker['bid']) > float(trade.price_at_execution):
                # Profitable sell opportunity! Sell what we bought back to original currency
                amount_to_sell = min(balances[currency_bought], balances[currency_bought] * Decimal(str(config.trade_size_percentage or 0.1)))
                
                if amount_to_sell > 0:
                    currency_to_get = pair_parts[0]
                    decision = {
                        'from': currency_bought,        # Sell EUR
                        'to': currency_to_get,         # Get USD
                        'amount': amount_to_sell,
                        'p_from': Decimal('1'),        # 1 EUR
                        'p_to': Decimal(str(current_ticker['bid'])),  # Gets this many USD
                        'conf': 0.9,
                        'pair': trade.pair
                    }
                    if self.execute_trade(decision):
                        executed.append(decision)
                    break  # Only sell one position per iteration

        # Look for buy opportunities
        opportunities = PortfolioOptimizer().find_all_opportunities(balances, tickers, config)
        for d in opportunities:
            if self.execute_trade(d):
                executed.append(d)
        
        return executed

    def execute_trade(self, d):
        try:
            with transaction.atomic():
                # Determine operation type based on what we're trading
                # The key insight: if we're trading d['from'] -> d['to']
                # and the pair is "A-B" where we're selling A to get B, that's a SELL
                
                crypto_currencies = ['BTC', 'ETH', 'LTC', 'XRP', 'ADA']
                
                pair_parts = d['pair'].split('-') if '-' in d['pair'] else d['pair']
                if isinstance(pair_parts, str):
                    pair_parts = [d['pair'][:3], d['pair'][3:]] if len(d['pair']) > 3 else [d['pair']]
                
                # Determine operation:
                # - If selling crypto (d['from'] is crypto) = SELL
                # - If buying crypto (d['to'] is crypto) = BUY
                # - If both fiat, check pair structure:
                #   If d['from'] appears FIRST in pair (e.g., EUR-USD and from=EUR) = SELL
                #   Otherwise = BUY
                
                if d['from'] in crypto_currencies:
                    # Selling crypto
                    op = "SELL"
                elif d['to'] in crypto_currencies:
                    # Buying crypto
                    op = "BUY"
                elif len(pair_parts) >= 2 and pair_parts[0] == d['from']:
                    # Both fiat: if from currency is first in pair, we're selling it
                    op = "SELL"
                else:
                    # Default: buying
                    op = "BUY"
                
                bal_from = UserBalance.objects.select_for_update().get(user_id=self.user_id, currency=d['from'])
                bal_to, _ = UserBalance.objects.select_for_update().get_or_create(user_id=self.user_id, currency=d['to'], defaults={'amount': 0})

                if bal_from.amount < d['amount']: return False

                received = (d['amount'] * d['p_from']) / d['p_to']
                bal_from.amount -= d['amount']
                bal_to.amount += received
                
                bal_from.save()
                bal_to.save()
                if bal_from.amount <= 0: bal_from.delete()

                # Calculate profit for SELL trades
                profit = None
                if op == "SELL":
                    # Get average buy price for the currency we're selling
                    buy_trades_for_currency = TradeHistory.objects.filter(
                        user_id=self.user_id,
                        operation="BUY",
                        pair__contains=d['from']  # Pair contains the currency we're selling
                    ).order_by('-timestamp')[:20]
                    
                    if buy_trades_for_currency.exists():
                        buy_prices = [float(t.price_at_execution) for t in buy_trades_for_currency]
                        avg_buy_price = sum(buy_prices) / len(buy_prices) if buy_prices else float(d['p_to'])
                        
                        # Profit = (sell_price - avg_buy_price) * amount_sold
                        profit = (float(d['p_to']) - avg_buy_price) * float(d['amount'])
                    else:
                        # No previous buys, assume profit is 0
                        profit = 0
                else:
                    # BUY trades have 0 profit until they're sold
                    profit = 0

                TradeHistory.objects.create(
                    user_id=self.user_id, pair=d['pair'], operation=op, amount=d['amount'],
                    price_at_execution=d['p_to'], status="EXECUTED", confidence_score=d['conf'],
                    profit=profit
                )
                print(f"✅ {op}: {d['from']} -> {d['to']} | Quantity: {received} | Profit: {profit}")
                return True
        except Exception as e:
            print(f"❌ Trade failed: {e}")
            import traceback
            traceback.print_exc()
            return False

    def refresh_all_tickers(self):
        try:
            tickers = self.api.get_all_tickers() or []
            allowed = ["BTC", "ETH", "EUR", "USD"]
            for t in tickers:
                p, c = t.get('pair'), t.get('currency')
                if p and any(m in p for m in allowed):
                    try:
                        ask, bid = Decimal(str(t['ask'])), Decimal(str(t['bid']))
                        PriceSnapshot.objects.create(pair=p, bid=bid, ask=ask, currency=c)
                        # Add slight variation to simulate market movement
                        v = ask * Decimal(random.uniform(0.01, 0.05))
                        PriceSnapshot.objects.create(pair=p, bid=bid + v, ask=ask - v, currency=c)
                    except Exception as e:
                        logger.warning(f"Failed to create snapshot for {p}: {e}")
                        continue
        except Exception as e:
            logger.error(f"Failed to fetch tickers: {e}")
            return False
        return True

class PortfolioOptimizer:
    def find_all_opportunities(self, holdings, tickers, config):
        moedas = ['BTC', 'ETH', 'EUR', 'USD']
        opportunities = []

        for cur_origem in holdings.keys():
            if holdings[cur_origem] <= 0: continue
            
            for cur_destino in moedas:
                if cur_origem == cur_destino: continue
                
                # Try different pair formats
                pair_formats = [
                    f"{cur_origem}-{cur_destino}",
                    f"{cur_origem}{cur_destino}",
                ]
                reverse_formats = [
                    f"{cur_destino}-{cur_origem}",
                    f"{cur_destino}{cur_origem}",
                ]
                
                # Find which format exists in tickers
                pair = None
                reverse_pair = None
                
                for fmt in pair_formats:
                    if fmt in tickers:
                        pair = fmt
                        break
                
                for fmt in reverse_formats:
                    if fmt in tickers:
                        reverse_pair = fmt
                        break
                
                if pair:
                    p_from, p_to = Decimal('1'), Decimal(str(tickers[pair]['ask']))
                    ret = float((Decimal(str(tickers[pair]['bid'])) - p_to) / p_to)
                    active_pair = pair
                elif reverse_pair:
                    p_from, p_to = Decimal(str(tickers[reverse_pair]['bid'])), Decimal('1')
                    ret = float((p_from - Decimal(str(tickers[reverse_pair]['ask']))) / Decimal(str(tickers[reverse_pair]['ask'])))
                    active_pair = reverse_pair
                else:
                    continue

                conf = max(0, min(1.0, ret * 25))
                if conf >= config.min_confidence_score:
                    opportunities.append({
                        'from': cur_origem, 'to': cur_destino, 
                        'amount': holdings[cur_origem] * Decimal(str(config.trade_size_percentage or 0.1)),
                        'p_from': p_from, 'p_to': p_to, 'conf': conf, 'pair': active_pair
                    })
        
        return sorted(opportunities, key=lambda x: x['conf'], reverse=True)[:2]

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
        self.thread = threading.Thread(target=self._run_loop, daemon=False)
        self.thread.start()
        self.logger.info("Bot started")

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=10)
        self.logger.info("Bot stopped")

    def _run_loop(self):
        print("🤖 Bot loop started!")
        thresholdSeconds = 15.0
        lastFullPull = time.monotonic()
        try:
            while self.running:
                try:
                    config = BotConfig.get_config()
                    if not config.is_active:
                        time.sleep(2)
                        continue
                        
                    now = time.monotonic()
                    if now - lastFullPull >= thresholdSeconds:
                        print("📊 Fetching tickers...")
                        self.bot.refresh_all_tickers()
                        lastFullPull = now
                        executed = self.bot.run_iteration()
                        if executed:
                            print(f"✅ Executed {len(executed)} trades")
                    
                    time.sleep(config.check_interval_seconds)
                except Exception as e:
                    print(f"⚠️ Error in iteration: {e}")
                    self.logger.error(f"Error in iteration: {e}", exc_info=True)
                    time.sleep(5)
        except Exception as e:
            print(f"❌ Fatal error in bot loop: {e}")
            self.logger.error(f"Fatal error in bot loop: {e}", exc_info=True)
            time.sleep(5)


    def is_running(self) -> bool:
        return self.running and self.thread and self.thread.is_alive()
