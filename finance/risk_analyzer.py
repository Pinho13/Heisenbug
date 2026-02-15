from decimal import Decimal
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

    def score(self) -> float:
        return (self.confidence ** 2) / (self.risk_score + 0.1)

class RiskAnalyzer:
    def __init__(self, window=10):
        self.window = window

    def calculate_volatility(self, pair_symbol: str) -> float:
        # Busca snapshots reais para calcular desvio padrão
        snapshots = PriceSnapshot.objects.filter(pair=pair_symbol).order_by('-timestamp')[:self.window]
        if len(snapshots) < 2:
            return 0.05
        
        prices = [float(s.ask) for s in snapshots]
        try:
            mean_p = statistics.mean(prices)
            return statistics.stdev(prices) / mean_p if mean_p > 0 else 0.05
        except:
            return 0.05

    def calculate_risk_score(self, expected_return: float, volatility: float, confidence: float) -> float:
        return (volatility * 0.6) + (1.0 - confidence) * 0.4

    def should_trade(self, risk_score, confidence, tolerance, min_conf) -> bool:
        return risk_score <= tolerance and confidence >= min_conf