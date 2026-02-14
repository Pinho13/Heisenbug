from django.conf import settings
import requests

class UpholdAPIHandler:
    BASE_URL = "https://api.uphold.com/v0"

    def __init__(self, api_key=None):

        actual_key = api_key or settings.UPHOLD_API_KEY
        self.headers = {}
        if actual_key:
            self.headers['Authorization'] = f'Bearer {actual_key}'

    # Market Data
    def get_ticker(self, currency_pair: str):
        url = f"{self.BASE_URL}/ticker/{currency_pair}"
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()  # 4xx/5xx errors
            return response.json()
        except requests.RequestException as e:
            # Handle network errors, timeouts, invalid responses
            print(f"Error fetching {currency_pair}: {e}")
            return None

    def get_all_tickers(self):
        url = f"{self.BASE_URL}/ticker"
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            print(f"Error fetching tickers: {e}")
            return None

    def get_accounts(self):
        """Fetch balances (requires API key)."""
        url = f"{self.BASE_URL}/accounts"
        try:
            response = requests.get(url, headers=self.headers, timeout = 10)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            print(f"[API ERROR] {e}")
            return None

    # Place Orders
    def place_order(self, currency, amount, operation="buy"):
        """Place a market order: 'buy' or 'sell'."""
        url = f"{self.BASE_URL}/orders"
        payload = {
            "denomination": currency.upper(),
            "amount": str(amount),
            "direction": operation
        }
        try:
            response = requests.post(url, headers=self.headers, json=payload, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            print(f"[ORDER ERROR] {e}")
            return None
