"""Risk analysis and volatility calculations."""
from decimal import Decimal
from collections import deque
from django.utils import timezone
import statistics


class RiskAnalyzer:
    """
    Analyzes market risk based on volatility and price movements.
    """

    def __init__(self, volatility_window: int = 10):
        """
        Args:
            volatility_window: Number of recent prices to consider for volatility
        """
        self.volatility_window = volatility_window
        self.price_history = deque(maxlen=volatility_window)

    def add_price(self, price: Decimal):
        """Record a price point."""
        self.price_history.append(float(price))

    def calculate_volatility(self) -> float:
        """
        Calculate volatility as coefficient of variation (std dev / mean).
        Returns value between 0 and 1 (normalized).
        
        Returns:
            Float: 0=no volatility, higher=more volatile
        """
        if len(self.price_history) < 2:
            return 0.0

        try:
            prices = list(self.price_history)
            mean_price = statistics.mean(prices)
            if mean_price == 0:
                return 0.0
            
            std_dev = statistics.stdev(prices)
            volatility = std_dev / mean_price
            
            # Cap at 1.0 for normalization
            return min(volatility, 1.0)
        except:
            return 0.0

    def calculate_price_momentum(self) -> float:
        """
        Calculate momentum (-1 to 1, where 1=strong uptrend, -1=strong downtrend).
        
        Returns:
            Float: -1 to 1
        """
        if len(self.price_history) < 2:
            return 0.0

        prices = list(self.price_history)
        first_price = prices[0]
        last_price = prices[-1]
        
        if first_price == 0:
            return 0.0

        # Normalized change
        change = (last_price - first_price) / first_price
        return max(-1.0, min(1.0, change))

    def calculate_risk_score(
        self, 
        potential_gain: float,
        volatility: float,
        confidence: float = 0.5
    ) -> float:
        """
        Calculate composite risk score (0-1).
        
        Higher volatility + lower potential gain = higher risk.
        
        Args:
            potential_gain: Expected return (0-1, where 0.05 = 5%)
            volatility: Market volatility (0-1)
            confidence: Confidence in the trade (0-1)
            
        Returns:
            Float: 0=low risk, 1=high risk
        """
        if potential_gain <= 0:
            return 1.0  # No upside = high risk

        # Risk = volatility / (confidence * gain)
        risk = volatility / max(confidence * max(potential_gain, 0.01), 0.01)
        
        # Normalize to 0-1
        return min(risk, 1.0)

    def should_trade(
        self,
        risk_score: float,
        confidence: float,
        risk_tolerance: float,
        min_confidence: float = 0.6
    ) -> bool:
        """
        Determine if a trade should be executed based on risk/confidence.
        
        Args:
            risk_score: Calculated risk score (0-1)
            confidence: Trade confidence (0-1)
            risk_tolerance: User's risk tolerance (0-1, 0=conservative)
            min_confidence: Minimum required confidence
            
        Returns:
            Bool: True if trade meets criteria
        """
        # Must meet minimum confidence
        if confidence < min_confidence:
            return False

        # Risk score must be below tolerance threshold
        # If risk_tolerance is 0.5, we accept risks up to 0.5
        # If risk_tolerance is 0.9, we're more willing to take risks
        max_acceptable_risk = risk_tolerance
        if risk_score > max_acceptable_risk:
            return False

        return True


class TradeDecision:
    """Represents a potential trade decision."""
    
    def __init__(
        self,
        from_pair: str,
        to_pair: str,
        amount: Decimal,
        from_price: Decimal,
        to_price: Decimal,
        confidence: float,
        risk_score: float,
        volatility: float,
        reason: str = ""
    ):
        self.from_pair = from_pair
        self.to_pair = to_pair
        self.amount = amount
        self.from_price = from_price
        self.to_price = to_price
        self.confidence = confidence
        self.risk_score = risk_score
        self.volatility = volatility
        self.reason = reason

    def expected_return(self) -> Decimal:
        """Calculate expected return amount."""
        if self.from_price == 0:
            return Decimal('0')
        from_value = self.amount * self.from_price
        to_value = from_value * (self.to_price / self.from_price) if self.from_price != 0 else Decimal('0')
        return to_value - from_value

    def expected_return_percent(self) -> float:
        """Calculate expected return as percentage."""
        if self.from_price == 0:
            return 0.0
        return float((self.to_price - self.from_price) / self.from_price)

    def score(self) -> float:
        """
        Composite score for ranking trades.
        Higher is better (high confidence + low risk).
        """
        # Score = (confidence^2) / (risk_score + 0.1)
        # The +0.1 prevents division by zero
        return (self.confidence ** 2) / (self.risk_score + 0.1)

    def __str__(self):
        return (
            f"{self.from_pair}→{self.to_pair}: "
            f"confidence={self.confidence:.2f}, risk={self.risk_score:.2f}, "
            f"expected_return={self.expected_return_percent():.2%}"
        )
