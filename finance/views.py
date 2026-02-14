from django.shortcuts import render
from django.http import JsonResponse
from .uphold_api import UpholdAPIHandler

def btc_usd_price(request):
    api = UpholdAPIHandler()
    ticker = api.get_ticker("BTC-USD")
    if ticker:
        return JsonResponse({
            "symbol": ticker.get("symbol"),
            "bid": ticker.get("bid"),
            "ask": ticker.get("ask"),
            "last": ticker.get("last"),
        })
    return JsonResponse({"error": "Could not fetch data"}, status=500)

def price_view(request, pair):
    """
    Fetch any currency/crypto pair dynamically from Uphold API.
    Example: /price/BTC-USD/
    """
    api = UpholdAPIHandler()
    ticker = api.get_ticker(pair.upper()) # lower case is a no no

    if ticker:
        return JsonResponse({
            "symbol": ticker.get("symbol"),
            "bid": ticker.get("bid"),
            "ask": ticker.get("ask"),
            "last": ticker.get("last"),
        })
    
    return JsonResponse({"error": f"Could not fetch data for {pair}"}, status=404)
