from django.shortcuts import render
from finance.uphold_api import UpholdAPIHandler
from finance.models import TradeHistory, BotConfig, PriceSnapshot
import logging

logger = logging.getLogger(__name__)

CURRENCIES = [
    {'symbol': 'EUR-USD', 'name': 'Euro / United States Dollar', 'icon': '€', 'color': 'bg-blue-500'},
    {'symbol': 'USD-EUR', 'name': 'United States Dollar / Euro', 'icon': '$', 'color': 'bg-green-500'},
    {'symbol': 'BTC-USD', 'name': 'Bitcoin / United States Dollar', 'icon': '₿', 'color': 'bg-orange-500'},
    {'symbol': 'ETH-USD', 'name': 'Ethereum / United States Dollar', 'icon': 'Ξ', 'color': 'bg-purple-500'},
]


def home(request):
    api = UpholdAPIHandler()

    # Fetch live prices for top currencies
    top_currencies = []
    for currency in CURRENCIES:
        try:
            ticker = api.get_ticker(currency['symbol'])
            if ticker:
                bid = float(ticker.get('bid', 0))
                ask = float(ticker.get('ask', 0))
                price = (bid + ask) / 2
                top_currencies.append({
                    'symbol': currency['symbol'],
                    'name': currency['name'],
                    'icon': currency['icon'],
                    'color': currency['color'],
                    'price': f'${price:,.2f}',
                    'bid': f'{bid:,.4f}',
                    'ask': f'{ask:,.4f}',
                })
        except Exception as e:
            logger.error(f"Error fetching {currency['symbol']}: {e}")

    # Fetch recent trades
    trades = TradeHistory.objects.order_by('-timestamp')[:10]

    # Fetch bot config
    try:
        config = BotConfig.get_config()
        risk_tolerance = config.risk_tolerance
        trade_size = config.trade_size_percentage
    except Exception:
        risk_tolerance = 0.5
        trade_size = 0.1

    context = {
        'top_currencies': top_currencies,
        'trades': trades,
        'risk_tolerance': risk_tolerance,
        'trade_size': trade_size,
    }

    return render(request, 'base.html', context)
