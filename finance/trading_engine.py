from decimal import Decimal
from .risk_analyzer import RiskAnalyzer, TradeDecision

class PortfolioOptimizer:
    def __init__(self, api_handler):
        self.api = api_handler
        self.risk_analyzers = {}

    def get_analyzer(self, pair):
        if pair not in self.risk_analyzers:
            self.risk_analyzers[pair] = RiskAnalyzer(window=10)
        return self.risk_analyzers[pair]

    def find_best_trade(self, portfolio, available_pairs, tickers, risk_tolerance, min_confidence, trade_size_amount=None, trade_size_percent=0.1):
        holdings = portfolio.get_all_holdings()
        best_decision = None

        for from_curr, balance in holdings.items():
            if balance <= 0: continue
            
            amount = Decimal(str(trade_size_amount)) if trade_size_amount else balance * Decimal(str(trade_size_percent))
            amount = min(amount, balance)

            for pair_symbol in available_pairs:
                if from_curr not in pair_symbol: continue
                
                # Identificar moeda de destino
                to_curr = pair_symbol.replace(from_curr, "").replace("-", "")
                ticker = tickers.get(pair_symbol)
                if not ticker: continue

                from_price = Decimal('1.0') # Simplificado para base USD
                to_price = Decimal(str(ticker['ask']))
                
                if to_price <= 0: continue

                # Cálculo de Retorno e Risco
                expected_return = float((Decimal(str(ticker['bid'])) - to_price) / to_price)
                analyzer = self.get_analyzer(pair_symbol)
                volatility = analyzer.calculate_volatility(pair_symbol)
                
                # Confiança: Retorno alto + Volatilidade baixa = +Confiança
                confidence = max(0, min(1.0, (expected_return * 5) - (volatility * 2)))
                risk_score = analyzer.calculate_risk_score(expected_return, volatility, confidence)

                if analyzer.should_trade(risk_score, confidence, risk_tolerance, min_confidence):
                    decision = TradeDecision(from_curr, to_curr, amount, from_price, to_price, confidence, risk_score, volatility, "Lucro detectado")
                    if not best_decision or decision.score() > best_decision.score():
                        best_decision = decision

        return best_decision