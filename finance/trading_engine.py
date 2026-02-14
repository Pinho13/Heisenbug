from decimal import Decimal
from typing import List, Dict, Tuple, Optional
from .risk_analyzer import RiskAnalyzer, TradeDecision
from .uphold_api import UpholdAPIHandler, PortfolioSnapshot
from .cache import MarketDataCache


class PortfolioOptimizer:
    """
    Analyzes all possible trades from current holdings
    and recommends the best one based on risk and return.
    """

    def __init__(self, api_handler: UpholdAPIHandler):
        self.api = api_handler
        self.cache = MarketDataCache()
        self.risk_analyzers: Dict[str, RiskAnalyzer] = {}

    def get_or_create_analyzer(self, pair: str) -> RiskAnalyzer:
        """Get or create risk analyzer for a pair."""
        if pair not in self.risk_analyzers:
            self.risk_analyzers[pair] = RiskAnalyzer(volatility_window=10)
        return self.risk_analyzers[pair]

    def update_price_history(self, pair: str, price: Decimal):
        """Update price history for volatility calculation."""
        analyzer = self.get_or_create_analyzer(pair)
        analyzer.add_price(price)

    def _get_conversion_rate(
        self,
        from_pair: str,
        to_pair: str,
        tickers: Dict[str, dict]
    ) -> Optional[Tuple[Decimal, Decimal]]:
        """
        Get conversion rate from from_pair to to_pair.

        Returns:
            Tuple of (from_price, to_price) or None
        """
        # direct pair
        direct_pair = f"{from_pair}-{to_pair}"
        if direct_pair in tickers:
            ticker = tickers[direct_pair]
            from_price = Decimal(str(ticker.get('ask', 0)))
            to_price = Decimal('1')  # Base currency price is always 1
            return (from_price, to_price)

        # reverse pair
        reverse_pair = f"{to_pair}-{from_pair}"
        if reverse_pair in tickers:
            ticker = tickers[reverse_pair]
            ask = Decimal(str(ticker.get('ask', 0)))
            if ask > 0:
                from_price = ask
                to_price = Decimal('1') / ask
                return (from_price, to_price)

        return None

    def generate_trade_opportunities(
        self,
        portfolio: PortfolioSnapshot,
        available_pairs: List[str],
        tickers: Dict[str, dict],
        trade_size_amount: Optional[Decimal] = None,
        trade_size_percent: float = 0.1
    ) -> List[TradeDecision]:
        """
        Generate all possible trades from current holdings.

        Args:
            portfolio: Current holdings
            available_pairs: List of tradeable pairs
            tickers: Dict of ticker data from API
            trade_size_amount: Fixed amount to trade (if set, overrides percent)
            trade_size_percent: Percentage of holdings to trade

        Returns:
            List of TradeDecision objects
        """
        trades = []
        holdings = portfolio.get_all_holdings()

        # For each currency we hold
        for from_currency, balance in holdings.items():
            if balance <= 0:
                continue

            # Determine trade amount
            if trade_size_amount:
                amount = min(trade_size_amount, balance)
            else:
                amount = balance * Decimal(str(trade_size_percent))
                amount = min(amount, balance)

            if amount <= 0:
                continue

            # Try converting to each other currency
            for to_currency in set([
                    c for pair in available_pairs for c in pair.split('-')]):
                if to_currency == from_currency:
                    continue

                # Get conversion rate
                rate_info = self._get_conversion_rate(
                    from_currency, to_currency, tickers
                )
                if not rate_info:
                    continue

                from_price, to_price = rate_info
                if from_price <= 0 or to_price <= 0:
                    continue

                # Calculate expected return
                from_value = amount * from_price
                to_value = from_value * (to_price / from_price)
                expected_return_pct = float(
                    (to_value - from_value) / from_value) if from_value > 0 else 0.0

                # Skip if no profit potential
                if expected_return_pct <= 0.001:  # Less than 0.1% gain
                    continue

                # Get volatility
                pair_key = f"{from_currency}-{to_currency}"
                analyzer = self.get_or_create_analyzer(pair_key)
                self.update_price_history(pair_key, from_price)
                volatility = analyzer.calculate_volatility()

                # Calculate confidence and risk
                confidence = self._calculate_confidence(
                    expected_return_pct, volatility)
                risk_score = analyzer.calculate_risk_score(
                    expected_return_pct, volatility, confidence
                )

                trade = TradeDecision(
                    from_pair=from_currency,
                    to_pair=to_currency,
                    amount=amount,
                    from_price=from_price,
                    to_price=to_price,
                    confidence=confidence,
                    risk_score=risk_score,
                    volatility=volatility,
                    reason=f"Potential {expected_return_pct:.2%} gain with {
                        volatility:.2f} volatility"
                )

                trades.append(trade)

        return trades

    def _calculate_confidence(self, expected_return_pct: float, volatility: float) -> float:
        """
        Calculate confidence score for a trade.

        Higher return + lower volatility = higher confidence.

        Args:
            expected_return_pct: Expected return percentage (-1 to 1)
            volatility: Volatility score (0 to 1)

        Returns:
            Confidence score (0 to 1)
        """
        # Base confidence from return potential
        return_confidence = min(abs(expected_return_pct) * 2, 1.0)

        # Reduce confidence by volatility
        volatility_penalty = volatility * 0.5
        confidence = max(return_confidence - volatility_penalty, 0.0)

        return min(confidence, 1.0)

    def rank_trades(self, trades: List[TradeDecision]) -> List[TradeDecision]:
        """Rank trades by score (highest first)."""
        return sorted(trades, key=lambda t: t.score(), reverse=True)

    def find_best_trade(
        self,
        portfolio: PortfolioSnapshot,
        available_pairs: List[str],
        tickers: Dict[str, dict],
        risk_tolerance: float = 0.5,
        min_confidence: float = 0.6,
        trade_size_amount: Optional[Decimal] = None,
        trade_size_percent: float = 0.1
    ) -> Optional[TradeDecision]:
        """
        Find the single best trade given constraints.

        Returns:
            Best TradeDecision or None if no suitable trade found
        """
        # Generate opportunities
        trades = self.generate_trade_opportunities(
            portfolio, available_pairs, tickers,
            trade_size_amount, trade_size_percent
        )

        if not trades:
            return None

        # Rank by score
        ranked = self.rank_trades(trades)

        # Find first trade that meets risk/confidence criteria
        analyzer = RiskAnalyzer()
        for trade in ranked:
            if analyzer.should_trade(
                trade.risk_score,
                trade.confidence,
                risk_tolerance,
                min_confidence
            ):
                return trade

        return None

    def get_top_n_trades(
        self,
        portfolio: PortfolioSnapshot,
        available_pairs: List[str],
        tickers: Dict[str, dict],
        n: int = 5,
        risk_tolerance: float = 0.5,
        min_confidence: float = 0.6,
        trade_size_amount: Optional[Decimal] = None,
        trade_size_percent: float = 0.1
    ) -> List[TradeDecision]:
        """
        Get top N trade opportunities that meet risk criteria.

        Returns:
            List of TradeDecision objects, sorted by score
        """
        trades = self.generate_trade_opportunities(
            portfolio, available_pairs, tickers,
            trade_size_amount, trade_size_percent
        )

        if not trades:
            return []

        ranked = self.rank_trades(trades)
        analyzer = RiskAnalyzer()

        # Filter by risk/confidence
        suitable = []
        for trade in ranked:
            if analyzer.should_trade(
                trade.risk_score,
                trade.confidence,
                risk_tolerance,
                min_confidence
            ):
                suitable.append(trade)
                if len(suitable) >= n:
                    break

        return suitable
