import requests
from decimal import Decimal
from django.core.cache import cache
from django.utils import timezone
from datetime import timedelta


class PortfolioSnapshot:
    """Represents current portfolio holdings."""
    
    def __init__(self, accounts_data: list):
        self.accounts = accounts_data or []
        self.holdings = {}
        self._parse_holdings()

    def _parse_holdings(self):
        """Parse account data into holdings dict."""
        for account in self.accounts:
            currency = account.get('currency')
            balance = account.get('balance')
            if currency and balance:
                try:
                    self.holdings[currency] = Decimal(str(balance))
                except:
                    pass

    def get_balance(self, currency: str) -> Decimal:
        """Get balance for a currency."""
        return self.holdings.get(currency, Decimal('0'))

    def get_all_holdings(self) -> dict:
        """Get all holdings."""
        return self.holdings.copy()

    def has_balance(self, currency: str, amount: Decimal) -> bool:
        """Check if we have sufficient balance."""
        return self.get_balance(currency) >= amount


class UpholdAPIHandler:
    BASE_URL = "https://api.uphold.com/v0"
    MAX_RETRIES = 3
    RETRY_DELAY = 0.5

    def __init__(self, api_key=None):
        self.headers = {}
        if api_key:
            self.headers['Authorization'] = f'Bearer {api_key}'
        self.api_key = api_key

    def _get_with_retry(self, url: str, timeout: int = 10):
        """GET request with retry logic."""
        for attempt in range(self.MAX_RETRIES):
            try:
                response = requests.get(url, headers=self.headers, timeout=timeout)
                response.raise_for_status()
                return response.json()
            except requests.RequestException as e:
                if attempt == self.MAX_RETRIES - 1:
                    print(f"[API ERROR] Failed after {self.MAX_RETRIES} retries: {e}")
                    return None
                import time
                time.sleep(self.RETRY_DELAY * (attempt + 1))
        return None

    def _post_with_retry(self, url: str, payload: dict, timeout: int = 10):
        """POST request with retry logic."""
        for attempt in range(self.MAX_RETRIES):
            try:
                response = requests.post(url, headers=self.headers, json=payload, timeout=timeout)
                response.raise_for_status()
                return response.json()
            except requests.RequestException as e:
                if attempt == self.MAX_RETRIES - 1:
                    print(f"[API ERROR] POST failed after {self.MAX_RETRIES} retries: {e}")
                    return None
                import time
                time.sleep(self.RETRY_DELAY * (attempt + 1))
        return None

    # Market Data
    def get_ticker(self, currency_pair: str):
        """Fetch ticker for a single pair."""
        url = f"{self.BASE_URL}/ticker/{currency_pair}"
        return self._get_with_retry(url)

    def get_tickers_batch(self, pairs: list) -> dict:
        """
        Fetch tickers for multiple pairs efficiently.
        
        Returns:
            Dict {pair: ticker_data}
        """
        result = {}
        for pair in pairs:
            ticker = self.get_ticker(pair)
            if ticker:
                result[pair] = ticker
        return result

    def get_all_tickers(self):
        """Fetch all available tickers."""
        url = f"{self.BASE_URL}/ticker"
        return self._get_with_retry(url)

    def get_accounts(self):
        """Fetch accounts/balances (requires API key)."""
        if not self.api_key:
            print("[WARNING] No API key provided, cannot fetch accounts")
            return None
        url = f"{self.BASE_URL}/me/accounts"
        return self._get_with_retry(url)

    def get_portfolio(self) -> PortfolioSnapshot:
        """
        Get current portfolio snapshot.
        
        Returns:
            PortfolioSnapshot object with holdings
        """
        accounts = self.get_accounts()
        return PortfolioSnapshot(accounts)

    def get_available_pairs(self) -> list:
        """
        Get list of available currency pairs from account.
        
        Returns:
            List of pairs like ["BTC-USD", "ETH-USD", ...]
        """
        tickers = self.get_all_tickers()
        if not tickers:
            return []
        
        # Extract unique pairs from ticker data
        pairs = []
        seen = set()
        for ticker in tickers:
            pair = ticker.get('symbol')
            if pair and pair not in seen:
                pairs.append(pair)
                seen.add(pair)
        return pairs

    # Place Orders
    def place_order(self, currency: str, amount, operation: str = "buy"):
        """
        Place a market order: 'buy' or 'sell'.
        
        Args:
            currency: Currency to buy/sell (e.g., "BTC")
            amount: Amount to trade
            operation: 'buy' or 'sell'
            
        Returns:
            Order response or None
        """
        if not self.api_key:
            print("[ERROR] Cannot place order without API key")
            return None

        url = f"{self.BASE_URL}/me/orders"
        payload = {
            "denomination": {"currency": currency.upper()},
            "amount": str(amount),
            "direction": operation
        }
        return self._post_with_retry(url, payload)

    def get_order_status(self, order_id: str):
        """Check status of a placed order."""
        if not self.api_key:
            return None
        url = f"{self.BASE_URL}/me/orders/{order_id}"
        return self._get_with_retry(url)
