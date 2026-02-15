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
    def __init__(self, window=10):
        self.window = window

    def calculate_volatility(self, pair_symbol: str) -> float:
        """Calcula a volatilidade real baseada nos snapshots da DB"""
        from finance.models import PriceSnapshot
        import statistics
        
        # Vai buscar os últimos X preços da base de dados
        snapshots = PriceSnapshot.objects.filter(pair=pair_symbol).order_by('-timestamp')[:self.window]
        
        if len(snapshots) < 2:
            return 0.05  # Volatilidade base se não houver histórico

        # Usamos o preço 'ask' para a média
        prices = [float(s.ask) for s in snapshots]
        
        try:
            mean_price = statistics.mean(prices)
            if mean_price == 0: return 0.05
            std_dev = statistics.stdev(prices)
            return min(std_dev / mean_price, 1.0)
        except:
            return 0.05

    def calculate_risk_score(self, expected_return: float, volatility: float, confidence: float) -> float:
        # Score de 0 a 1: quanto mais alto, mais risco
        return (volatility * 0.6) + (1 - confidence) * 0.4

    def should_trade(self, risk_score: float, confidence: float, tolerance: float, min_conf: float) -> bool:
        return risk_score <= tolerance and confidence >= min_conf