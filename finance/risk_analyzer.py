from decimal import Decimal
from collections import deque
import statistics
from finance.models import PriceSnapshot


class TradeDecision:
    def __init__(self, from_pair, to_pair, amount, from_price, to_price, confidence, risk_score, volatility, reason):
        self.from_pair = from_pair
        self.to_pair = to_pair
        self.amount = Decimal(str(amount))
        self.from_price = Decimal(str(from_price))
        self.to_price = Decimal(str(to_price))
        self.confidence = float(confidence)
        self.risk_score = float(risk_score)
        self.volatility = float(volatility)
        self.reason = reason

    def expected_return(self) -> Decimal:
        if self.from_price == 0:
            return Decimal('0')
        from_value = self.amount * self.from_price
        to_value = from_value * \
            (self.to_price / self.from_price) if self.from_price != 0 else Decimal('0')
        return to_value - from_value

    def expected_return_percent(self) -> float:
        if self.from_price == 0:
            return 0.0
        return float((self.to_price - self.from_price) / self.from_price)

    def score(self) -> float:
        """
        Composite score, higher is better
        """
        return (self.confidence ** 2) / (self.risk_score + 0.1)

    def __str__(self):
        return (
            f"{self.from_pair}->{self.to_pair}: "
            f"confidence={self.confidence:.2f}, risk= {self.risk_score:.2f}, "
            f"expected_return={self.expected_return_percent():.2%} "
        )


class RiskAnalyzer:
    def __init__(self, volatility_window=10):
        self.volatility_window = volatility_window
        self.price_history = deque(maxlen=volatility_window)

    def add_price(self, price: Decimal):
        """Record a price point"""
        self.price_history.append(float(price))

    def calculate_volatility(self) -> float:
        """returns float: 0 is no volatility, increases with volatility"""
        if len(self.price_history) < 2:
            return 0.0
        try:
            prices = list(self.price_history)
            mean_price = statistics.mean(prices)
            if mean_price == 0:
                return 0.0
            std_dev = statistics.stdev(prices)
            volatility = std_dev / mean_price
            return min(volatility, 1.0)
        except Exception:
            return 0.0

    def calculate_price_momentum(self) -> float:
        """float -1 to 1"""
        if len(self.price_history) < 2:
            return 0.0
        prices = list(self.price_history)
        first_price = prices[0]
        last_price = prices[-1]

        if first_price == 0:
            return 0.0

        change = (last_price - first_price) / first_price
        return max(-1.0, min(1.0, change))

    def calculate_risk_score(
        self,
        potential_gain: float,
        volatility: float,
        confidence: float = 0.5
    ) -> float:
        """Calculates risk, Float from 0 to 1, 1 being high risk"""
        if potential_gain <= 0:
            return 1.0  # no upside is high risk

        risk = volatility / max(confidence * max(potential_gain, 0.01), 0.01)
        return min(risk, 1.0)

    def should_trade(
        self,
        risk_score: float,
        confidence: float,
        risk_tolerance: float,
        min_confidence: float = 0.6
    ) -> bool:
        """returns true if trade meets criteria"""
        if confidence < min_confidence:
            return False

        max_acceptable_risk = risk_tolerance
        if risk_score > max_acceptable_risk:
            return False

        return True
    def calculate_volatility(self, pair_symbol) -> float:
        snapshots = PriceSnapshot.objects.filter(pair=pair_symbol).order_by('-timestamp')[:self.window]
        prices = [float(s.last) for s in snapshots]

        if len(prices) < 2:
            return 0.05 

        return statistics.stdev(prices) / statistics.mean(prices)
    
    def calculate_risk_score(self, expected_return, volatility, confidence) -> float:
        return (volatility * 0.5) + (1 - confidence) * 0.5

    def should_trade(self, risk_score, confidence, tolerance, min_conf) -> bool:
        return risk_score <= tolerance and confidence >= min_conf
