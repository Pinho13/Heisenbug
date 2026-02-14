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

    def score(self):
        return self.confidence * (1 - self.risk_score)

class RiskAnalyzer:
    def __init__(self, volatility_window=10):
        self.price_history = {}
        self.window = volatility_window

    def add_price(self, price: Decimal):
        pass

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
