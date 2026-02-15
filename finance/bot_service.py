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

        # Load the latest snapshot per (pair, source) so we can compare sources
        tickers_by_source = {}  # {pair: {source: {ask, bid}}}
        for snap in PriceSnapshot.objects.values('pair', 'source').distinct():
            pair, source = snap['pair'], snap['source']
            latest = PriceSnapshot.objects.filter(pair=pair, source=source).order_by('-timestamp').first()
            if latest:
                tickers_by_source.setdefault(pair, {})[source] = {'ask': latest.ask, 'bid': latest.bid}

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
                        # Simulate a second exchange whose price level is slightly
                        # shifted from the real one (same spread, different mid-price).
                        # Real cross-exchange differences are typically 0.05–0.15%.
                        shift = ask * Decimal(random.uniform(-0.0015, 0.0015))
                        PriceSnapshot.objects.create(pair=p, bid=bid + shift, ask=ask + shift, currency=c, source='simulated')
                    except Exception as e:
                        logger.warning(f"Failed to create snapshot for {p}: {e}")
                        continue
        except Exception as e:
            logger.error(f"Failed to fetch tickers: {e}")
            return False
        return True

class PortfolioOptimizer:
    def find_all_opportunities(self, holdings, tickers_by_source, config):
        """Find arbitrage opportunities across sources for the same pair.

        For each pair that has prices from two or more sources, check whether
        one source's bid (sell price) exceeds another source's ask (buy price).
        If so, we can buy cheap and sell expensive simultaneously.

        tickers_by_source: {pair: {source: {ask, bid}}}
        """
        bot_config = BotConfig.get_config()
        moedas = [c.strip() for c in bot_config.selected_currencies.split(',') if c.strip()]
        if not moedas:
            moedas = ['BTC', 'ETH', 'EUR', 'USD']
        opportunities = []

        for cur_origem in holdings.keys():
            if holdings[cur_origem] <= 0:
                continue

            for cur_destino in moedas:
                if cur_origem == cur_destino:
                    continue

                # Try different pair formats
                pair_formats = [
                    f"{cur_origem}-{cur_destino}",
                    f"{cur_origem}{cur_destino}",
                ]
                reverse_formats = [
                    f"{cur_destino}-{cur_origem}",
                    f"{cur_destino}{cur_origem}",
                ]

                pair = None
                reverse_pair = None

                for fmt in pair_formats:
                    if fmt in tickers_by_source:
                        pair = fmt
                        break
                for fmt in reverse_formats:
                    if fmt in tickers_by_source:
                        reverse_pair = fmt
                        break

                active_pair = pair or reverse_pair
                if not active_pair:
                    continue

                sources = tickers_by_source[active_pair]
                if len(sources) < 2:
                    continue

                # Find the best arbitrage: lowest ask (buy cheap) vs highest bid (sell expensive)
                source_list = list(sources.items())
                best_buy = min(source_list, key=lambda s: s[1]['ask'])   # cheapest ask
                best_sell = max(source_list, key=lambda s: s[1]['bid'])  # highest bid

                buy_ask = best_buy[1]['ask']
                sell_bid = best_sell[1]['bid']

                # Only trade if there's a positive spread (sell_bid > buy_ask)
                if sell_bid <= buy_ask:
                    continue

                spread_pct = float(sell_bid - buy_ask) / float(buy_ask)

                # p_from / p_to encode how the 'from' currency converts via this pair
                if pair:
                    p_from = buy_ask
                    p_to = Decimal('1')
                else:
                    p_from = Decimal('1')
                    p_to = buy_ask

                # Any positive spread is guaranteed profit for arbitrage.
                # Scale so that a 0.01% spread already reaches high confidence.
                conf = max(0, min(1.0, spread_pct * 5000))
                if conf >= config.min_confidence_score:
                    opportunities.append({
                        'from': cur_origem, 'to': cur_destino,
                        'amount': holdings[cur_origem] * Decimal(str(config.trade_size_percentage or 0.1)),
                        'buy_ask': buy_ask, 'sell_bid': sell_bid,
                        'p_from': p_from, 'p_to': p_to,
                        'conf': conf, 'pair': active_pair
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
        ticker_refresh_interval = 15.0
        # Start at 0 so the first ticker pull + trade happens immediately
        lastFullPull = 0
        try:
            while self.running:
                try:
                    config = BotConfig.get_config()
                    if not config.is_active:
                        self._interruptible_sleep(2)
                        continue

                    now = time.monotonic()
                    if now - lastFullPull >= ticker_refresh_interval:
                        print("📊 Fetching tickers...")
                        self.bot.refresh_all_tickers()
                        lastFullPull = now

                    # Always try to trade using whatever snapshots exist
                    executed = self.bot.run_iteration()
                    if executed:
                        print(f"✅ Executed {len(executed)} trades")

                    # Sleep 10 seconds between iterations (responsive enough
                    # for a dashboard, light enough on the DB)
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
