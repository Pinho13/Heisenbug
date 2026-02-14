"""Advanced trading bot with decision engine."""
from decimal import Decimal
from typing import Optional, Dict, List
import threading
import time
import logging

from django.utils import timezone
from .uphold_api import UpholdAPIHandler, PortfolioSnapshot
from .trading_engine import PortfolioOptimizer, TradeDecision
from .cache import MarketDataCache
from .models import TradeHistory, BotConfig, TradingPair, PriceSnapshot

logger = logging.getLogger(__name__)


class AdvancedTradeBot:
    """
    Advanced trading bot that:
    - Analyzes all possible trades
    - Applies risk filtering
    - Executes only high-confidence trades
    - Logs all decisions
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api = UpholdAPIHandler(api_key)
        self.optimizer = PortfolioOptimizer(self.api)
        self.cache = MarketDataCache()
        self.logger = logger

    def fetch_market_data(
        self,
        pairs: List[str],
        force_refresh: bool = False,
        ttl_seconds: int = 3
    ) -> Dict[str, dict]:
        """
        Fetch market data, using cache when possible.
        
        Args:
            pairs: List of pairs to fetch
            force_refresh: Ignore cache and refresh all
            ttl_seconds: Cache TTL
            
        Returns:
            Dict {pair: ticker_data}
        """
        to_fetch = []
        result = {}

        # Check cache first (unless force_refresh)
        if not force_refresh:
            cached = self.cache.get_all_prices(pairs, ttl_seconds)
            result.update(cached)
            to_fetch = [p for p in pairs if p not in cached]
        else:
            to_fetch = pairs

        # Fetch missing/stale data from API
        if to_fetch:
            fresh_data = self.api.get_tickers_batch(to_fetch)
            for pair, ticker in fresh_data.items():
                self.cache.set_price(pair, ticker, ttl_seconds)
                result[pair] = ticker
                self._store_price_snapshot(pair, ticker)

        return result

    def _store_price_snapshot(self, pair: str, ticker: dict):
        """Store price snapshot in DB for history."""
        try:
            from decimal import Decimal
            snapshot, _ = PriceSnapshot.objects.get_or_create(pair=pair)
            snapshot.bid = Decimal(str(ticker.get('bid', 0)))
            snapshot.ask = Decimal(str(ticker.get('ask', 0)))
            snapshot.last = Decimal(str(ticker.get('last', 0)))
            snapshot.save()
        except Exception as e:
            self.logger.warning(f"Failed to store price snapshot: {e}")

    def execute_trade(
        self,
        decision: TradeDecision,
        config: BotConfig
    ) -> bool:
        """
        Execute a trade decision.
        
        Args:
            decision: TradeDecision to execute
            config: Bot configuration
            
        Returns:
            Bool: True if successful
        """
        try:
            self.logger.info(
                f"Executing trade: {decision.from_pair}→{decision.to_pair}, "
                f"amount={decision.amount}, confidence={decision.confidence:.2f}"
            )

            # Place the order (in real scenario, this would be placed on exchange)
            # For now, we simulate success
            result = self.api.place_order(
                decision.to_pair,
                decision.amount,
                "buy"
            )

            # Log to database
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
        Run one trading iteration:
        1. Fetch market data
        2. Get current portfolio
        3. Find best trade
        4. Execute if confidence is high
        
        Returns:
            TradeDecision if executed, None otherwise
        """
        try:
            # Get config
            config = BotConfig.get_config()
            if not config.is_active:
                self.logger.info("Bot is inactive")
                return None

            # Get enabled trading pairs
            enabled_pairs = list(
                TradingPair.objects.filter(is_enabled=True).values_list(
                    'pair_symbol', flat=True
                )
            )

            if not enabled_pairs:
                self.logger.warning("No trading pairs enabled")
                return None

            # Fetch market data
            tickers = self.fetch_market_data(
                enabled_pairs,
                ttl_seconds=config.cache_ttl_seconds
            )

            if not tickers:
                self.logger.warning("Failed to fetch market data")
                return None

            # Get current portfolio
            portfolio = self.api.get_portfolio()
            if not portfolio or not portfolio.get_all_holdings():
                self.logger.warning("Could not fetch portfolio")
                return None

            # Find best trade
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
                    # Cleanup old trades
                    TradeHistory.cleanup_old_trades(keep_count=100)
                    return decision

            else:
                self.logger.debug("No suitable trades found")

            return None

        except Exception as e:
            self.logger.error(f"Error in trading iteration: {e}", exc_info=True)
            return None


class BotRunner:
    """Manages bot execution loop."""

    def __init__(self, api_key: Optional[str] = None):
        self.bot = AdvancedTradeBot(api_key)
        self.running = False
        self.thread = None
        self.logger = logger

    def start(self):
        """Start the bot loop in a background thread."""
        if self.running:
            self.logger.warning("Bot is already running")
            return

        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=False)
        self.thread.start()
        self.logger.info("Bot started")

    def stop(self):
        """Stop the bot loop."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=10)
        self.logger.info("Bot stopped")

    def _run_loop(self):
        """Main bot execution loop."""
        while self.running:
            try:
                config = BotConfig.get_config()
                
                # Run one iteration
                self.bot.run_iteration()

                # Sleep for configured interval
                time.sleep(config.check_interval_seconds)

            except Exception as e:
                self.logger.error(f"Error in bot loop: {e}", exc_info=True)
                time.sleep(5)  # Wait before retry

    def is_running(self) -> bool:
        """Check if bot is running."""
        return self.running and self.thread and self.thread.is_alive()
