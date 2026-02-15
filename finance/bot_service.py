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

        # Fetch live prices from the Uphold API instead of using stale DB snapshots
        allowed = [c.strip() for c in config.selected_currencies.split(',') if c.strip()]
        if not allowed:
            allowed = ["BTC", "ETH", "EUR", "USD"]

        # Skip inverse pairs like USDBTC/USDETH — their tiny values cause
        # precision issues.  We trade BTCUSD/ETHUSD instead.
        skip_pairs = {'USDBTC', 'USDETH'}

        tickers = self.api.get_all_tickers() or []
        tickers_by_source = {}  # {pair: {source: {ask, bid}}}
        for t in tickers:
            p = t.get('pair')
            if not p or p in skip_pairs or not any(m in p for m in allowed):
                continue
            try:
                ask = Decimal(str(t['ask']))
                bid = Decimal(str(t['bid']))
            except Exception:
                continue

            tickers_by_source.setdefault(p, {})['uphold'] = {'ask': ask, 'bid': bid}

            # Simulate a second exchange with independent shifts on bid and ask.
            # The ask is shifted down and the bid up so the simulated exchange
            # can offer a tighter (sometimes inverted) spread compared to the
            # real one, which is what creates cross-exchange arbitrage.
            ask_shift = ask * Decimal(str(random.uniform(-0.008, 0.002)))
            bid_shift = bid * Decimal(str(random.uniform(-0.002, 0.008)))
            tickers_by_source[p]['simulated'] = {'ask': ask + ask_shift, 'bid': bid + bid_shift}

            # Also save snapshots so the dashboard/history stays up to date
            c = t.get('currency', '')
            sim = tickers_by_source[p]['simulated']
            PriceSnapshot.objects.create(pair=p, bid=bid, ask=ask, currency=c, source='uphold')
            PriceSnapshot.objects.create(pair=p, bid=sim['bid'], ask=sim['ask'], currency=c, source='simulated')

        balances = {b.currency: b.amount for b in UserBalance.objects.filter(user_id=self.user_id)}

        # Find arbitrage opportunities and execute BUY+SELL simultaneously
        executed = []
        opportunities = PortfolioOptimizer().find_all_opportunities(balances, tickers_by_source, config)
        for d in opportunities:
            if self.execute_trade(d):
                executed.append(d)

        return executed

    def execute_trade(self, d):
        """Execute an arbitrage round-trip: buy at source A's ask, sell at source B's bid.

        The round-trip works the same regardless of pair direction:
          1. Buy the pair's base currency at the cheap source's ask
          2. Sell it immediately at the expensive source's bid
          returned = amount * sell_bid / buy_ask  (always in 'from' currency)
        """
        try:
            with transaction.atomic():
                buy_ask = d['buy_ask']
                sell_bid = d['sell_bid']

                bal_from = UserBalance.objects.select_for_update().get(user_id=self.user_id, currency=d['from'])
                if bal_from.amount < d['amount']:
                    return False

                # Round-trip: spend d['amount'], get back amount * (sell_bid / buy_ask)
                # The ratio sell_bid/buy_ask > 1 guarantees profit (checked in optimizer)
                returned = d['amount'] * sell_bid / buy_ask
                profit = returned - d['amount']

                # Net effect on balance: spent d['amount'], got back 'returned'
                bal_from.amount -= d['amount']
                bal_from.amount += returned
                bal_from.save()
                if bal_from.amount <= 0:
                    bal_from.delete()

                # Record BUY leg
                TradeHistory.objects.create(
                    user_id=self.user_id, pair=d['pair'], operation="BUY",
                    amount=d['amount'], price_at_execution=buy_ask,
                    status="EXECUTED", confidence_score=d['conf'], profit=0
                )
                # Record SELL leg
                TradeHistory.objects.create(
                    user_id=self.user_id, pair=d['pair'], operation="SELL",
                    amount=d['amount'], price_at_execution=sell_bid,
                    status="EXECUTED", confidence_score=d['conf'], profit=profit
                )
                print(f"✅ ARB {d['pair']}: buy@{buy_ask} sell@{sell_bid} | spent={d['amount']} returned={returned:.2f} | profit={profit:.4f}")
                return True
        except Exception as e:
            print(f"❌ Trade failed: {e}")
            import traceback
            traceback.print_exc()
            return False

    def refresh_all_tickers(self):
        try:
            tickers = self.api.get_all_tickers() or []
            # Use user-selected currencies from BotConfig instead of hardcoded list
            config = BotConfig.get_config()
            allowed = [c.strip() for c in config.selected_currencies.split(',') if c.strip()]
            if not allowed:
                allowed = ["BTC", "ETH", "EUR", "USD"]
            for t in tickers:
                p, c = t.get('pair'), t.get('currency')
                if p and any(m in p for m in allowed):
                    try:
                        ask, bid = Decimal(str(t['ask'])), Decimal(str(t['bid']))
                        PriceSnapshot.objects.create(pair=p, bid=bid, ask=ask, currency=c, source='uphold')
                        # Simulate a second exchange with independent bid/ask shifts
                        ask_shift = ask * Decimal(str(random.uniform(-0.008, 0.002)))
                        bid_shift = bid * Decimal(str(random.uniform(-0.002, 0.008)))
                        PriceSnapshot.objects.create(pair=p, bid=bid + bid_shift, ask=ask + ask_shift, currency=c, source='simulated')
                    except Exception as e:
                        logger.warning(f"Failed to create snapshot for {p}: {e}")
                        continue
        except Exception as e:
            logger.error(f"Failed to fetch tickers: {e}")
            return False
        return True

class PortfolioOptimizer:
    # Each selected currency maps to exactly one tradeable pair and the
    # balance currency used to fund the round-trip.
    # pair_name: the Uphold ticker symbol
    # from_currency: the balance we spend and get back in the round-trip
    CURRENCY_TO_PAIR = {
        'BTC': ('BTCUSD', 'USD'),
        'ETH': ('ETHUSD', 'USD'),
        'EUR': ('EURUSD', 'EUR'),
        'USD': ('USDEUR', 'USD'),
    }

    def find_all_opportunities(self, holdings, tickers_by_source, config):
        """Find arbitrage opportunities across sources for the same pair.

        For each selected currency, look up its canonical pair and check
        whether one source's bid exceeds another source's ask.

        tickers_by_source: {pair: {source: {ask, bid}}}
        """
        bot_config = BotConfig.get_config()
        selected = [c.strip() for c in bot_config.selected_currencies.split(',') if c.strip()]
        if not selected:
            selected = ['BTC', 'ETH', 'EUR', 'USD']
        opportunities = []

        for currency in selected:
            mapping = self.CURRENCY_TO_PAIR.get(currency)
            if not mapping:
                continue
            pair_name, from_currency = mapping

            if from_currency not in holdings or holdings[from_currency] <= 0:
                continue

            sources = tickers_by_source.get(pair_name)
            if not sources or len(sources) < 2:
                continue

            # Find the best arbitrage: lowest ask (buy cheap) vs highest bid (sell expensive)
            source_list = list(sources.items())
            best_buy = min(source_list, key=lambda s: s[1]['ask'])
            best_sell = max(source_list, key=lambda s: s[1]['bid'])

            buy_ask = best_buy[1]['ask']
            sell_bid = best_sell[1]['bid']

            if sell_bid <= buy_ask:
                continue

            spread_pct = float(sell_bid - buy_ask) / float(buy_ask)
            conf = max(0, min(1.0, spread_pct * 5000))

            if conf >= config.min_confidence_score:
                opportunities.append({
                    'from': from_currency, 'to': currency,
                    'amount': holdings[from_currency] * Decimal(str(config.trade_size_percentage or 0.1)),
                    'buy_ask': buy_ask, 'sell_bid': sell_bid,
                    'p_from': buy_ask, 'p_to': Decimal('1'),
                    'conf': conf, 'pair': pair_name
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

        # Recreate TradeBot to pick up latest config (bot_user, etc.)
        self.bot = TradeBot()
        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        self.logger.info("Bot started")

    def stop(self):
        self.running = False
        # Don't block — the loop checks self.running every second
        self.logger.info("Bot stopped")

    def _interruptible_sleep(self, seconds):
        """Sleep in 1-second increments so we can respond to stop quickly."""
        end = time.monotonic() + seconds
        while self.running and time.monotonic() < end:
            time.sleep(1)

    def _run_loop(self):
        print("🤖 Bot loop started!")
        try:
            while self.running:
                try:
                    config = BotConfig.get_config()
                    if not config.is_active:
                        self._interruptible_sleep(2)
                        continue

                    # run_iteration() now fetches live prices from the API,
                    # generates the simulated source, saves snapshots, and trades
                    # — all in one step with fresh data every cycle.
                    print("📊 Fetching live prices & trading...")
                    executed = self.bot.run_iteration()
                    if executed:
                        print(f"✅ Executed {len(executed)} trades")

                    # Sleep 10 seconds between iterations
                    self._interruptible_sleep(10)
                except Exception as e:
                    print(f"⚠️ Error in iteration: {e}")
                    self.logger.error(f"Error in iteration: {e}", exc_info=True)
                    self._interruptible_sleep(5)
        except Exception as e:
            print(f"❌ Fatal error in bot loop: {e}")
            self.logger.error(f"Fatal error in bot loop: {e}", exc_info=True)


    def is_running(self) -> bool:
        return self.running and self.thread and self.thread.is_alive()
