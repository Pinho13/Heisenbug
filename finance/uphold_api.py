import requests

class UpholdAPIHandler:
    BASE_URL = "https://api.uphold.com/v0"

    def __init__(self, api_key=None):
        self.headers = {}
        if api_key:
            self.headers['Authorization'] = f'Bearer {api_key}'

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
