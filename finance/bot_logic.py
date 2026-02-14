from .uphold_api import UpholdAPIHandler


class SimpleBot:
    """
    Skeleton bot for fetching prices and executing basic trades.
    """

    def __init__(self, api_key=None):
        # Initialize API handler
        self.api = UpholdAPIHandler(api_key)

    def check_price_and_trade(self, pair, buy_threshold, sell_threshold):
        """
        Fetch price and decide whether to buy or sell.
        """
        ticker = self.api.get_ticker(pair.upper())
        if not ticker:
            print(f"[ERROR] Could not fetch ticker for {pair}")
            return

        price = float(ticker.get("ask"))
        print(f"[INFO] {pair} price: {price}")

        # Simple threshold-based strategy
        if price < buy_threshold:
            print(f"[ACTION] Buying 1 {pair.split('-')[0]} at {price}")
            order = self.api.place_order(pair.split('-')[0], 1, "buy")
            print(f"[ORDER] {order}")
        elif price > sell_threshold:
            print(f"[ACTION] Selling 1 {pair.split('-')[0]} at {price}")
            order = self.api.place_order(pair.split('-')[0], 1, "sell")
            print(f"[ORDER] {order}")
        else:
            print("[ACTION] No trade, price within thresholds")
