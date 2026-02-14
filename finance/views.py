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
