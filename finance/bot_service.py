from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from typing import Optional, Dict, List
import threading
import time
import logging

from django.utils import timezone
from .uphold_api import UpholdAPIHandler
from .trading_engine import PortfolioOptimizer, TradeDecision
from .cache import MarketDataCache
from .models import TradeHistory, BotConfig, TradingPair, PriceSnapshot

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
                self.cache.set_price(pair, ticker, ttl_seconds)
                result[pair] = ticker
                self._store_price_snapshot(pair, ticker)
        return result

    def _store_price_snapshot(self, pair: str, ticker: dict):
        try:
            PriceSnapshot.objects.create(
                pair=pair,
                bid=Decimal(str(ticker.get('bid', 0))),
                ask=Decimal(str(ticker.get('ask', 0))),
                last=Decimal(str(ticker.get('last', 0)))
            )
        except Exception as e:
            self.logger.warning(f"Error storing price snapshot: {e}")

    def execute_trade(
        self,
        decision: TradeDecision,
        config: BotConfig
    ) -> bool:
        """Execute a trade decision
        Returns true if successful
        """
        try:
            self.logger.info(
                f"Executing trade: {decision.from_pair}->{decision.to_pair}, "
                f"amount={decision.amount}, confidence={
                    decision.confidence:.2f}"
            )
            result = self.api.place_order(
                decision.to_pair,
                decision.amount,
                "buy"
            )
            trade_record = TradeHistory.objects.create(
                from_pair=decision.from_pair,
                to_pair=decision.to_pair,
                decision="BUY",
                status="EXECUTED" if result else "FAILED",
                amount=decision.amount,
                from_price=decision.from_price,
                to_price=decision.to_price,
                confidence_score=decision.confidence,
                risk_score=decision.risk_score,
                volatility=decision.volatility,
                reason=decision.reason,
                result=str(result) if result else "API request failed",
                executed_at=timezone.now()
            )

            self.logger.info(f"Trade recorded: {trade_record}")
            return result is not None
        except Exception as e:
            self.logger.error(f"Failed to execute trade: {e}")
            TradeHistory.objects.create(
                from_pair=decision.from_pair,
                to_pair=decision.to_pair,
                decision="BUY",
                status="FAILED",
                amount=decision.amount,
                from_price=decision.from_price,
                to_price=decision.to_price,
                confidence_score=decision.confidence,
                risk_score=decision.risk_score,
                volatility=decision.volatility,
                reason=decision.reason,
                result=f"Exception: {str(e)}"
            )
            return False

    def run_iteration(self) -> Optional[TradeDecision]:
        """
        Trade iteration:
        -> Fetch market data
        -> get current portfolio
        -> find best trade
        -> execute if confidence is high

        Return: TradeDecision if executed, None otherwise
        """
        try:
            config = BotConfig.get_config()
            if not config.is_active:
                self.logger.info("Bot is inactive")
                return None

            enabled_pairs = list(
                TradingPair.objects.filter(is_enabled=True).values_list(
                    'pair_symbol', flat=True
                )
            )

            if not enabled_pairs:
                self.logger.warning("No trading pairs enabled")
                return None

            tickers = self.fetch_market_data(
                enabled_pairs,
                ttl_seconds=config.cache_ttl_seconds
            )

            if not tickers:
                self.logger.warning("Failed to fetch market data")
                return None

            portfolio = self.api.get_portfolio()
            if not portfolio or not portfolio.get_all_holdings():
                self.logger.warning("Could not fetch portfolio")
                return None

            trade_size = (
                config.trade_size_amount
                if config.trade_size_amount and config.trade_size_amount > 0
                else None
            )

            decision = self.optimizer.find_best_trade(
                portfolio=portfolio,
                available_pairs=enabled_pairs,
                tickers=tickers,
                risk_tolerance=config.risk_tolerance,
                min_confidence=config.min_confidence_score,
                trade_size_amount=trade_size,
                trade_size_percent=config.trade_size_percentage
            )

            if decision:
                self.logger.info(f"Found trade opportunity: {decision}")
                executed = self.execute_trade(decision, config)
                if executed:
                    TradeHistory.cleanup_old_trades(keep_count=100)
                    return decision
            else:
                self.logger.debug("No suitable trades found")

            return None
        except Exception as e:
            self.logger.error(f"Error in trading iteration: {
                              e}", exc_info=True)
            return None

    def refresh_all_tickers(self) -> None:
        try:
            tickers = self.api.get_all_tickers()
            if not tickers:
                self.logger.warning("Full thicker refresh returned no data")
                return
            for pair, ticker in tickers.items():
                self._store_price_snapshot(pair, ticker)
            self.logger.debug(
                f"Refreshed {len(tickers)} ticker snapshots"
            )

        except Exception as e:
            self.logger.warning(
                f"Failed full ticker refresh: {e}",
                exc_info=True
            )


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
        thresholdSeconds = 15.0
        lastFullPull = time.monotonic()
        try:
            config = BotConfig.get_config()
            self.bot.run_iteration()
            now = time.monotonic()
            if now - lastFullPull >= thresholdSeconds:
                self.bot.refresh_all_tickers()
                lastFullPull = now
            time.sleep(config.check_interval_seconds)
        except Exception as e:
            self.logger.error(
                f"Error in bot loop: {e}",
                exc_info=True
            )
            time.sleep(5)

    def is_running(self) -> bool:
        return self.running and self.thread and self.thread.is_alive()
