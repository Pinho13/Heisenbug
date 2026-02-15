from django.shortcuts import render
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from finance.uphold_api import UpholdAPIHandler
from finance.models import TradeHistory, BotConfig, PriceSnapshot
import logging
import json
import os

logger = logging.getLogger(__name__)

CURRENCIES = [
    {'symbol': 'EUR-USD', 'name': 'Euro / United States Dollar', 'icon': '€', 'color': 'bg-blue-500'},
    {'symbol': 'USD-EUR', 'name': 'United States Dollar / Euro', 'icon': '$', 'color': 'bg-green-500'},
    {'symbol': 'BTC-USD', 'name': 'Bitcoin / United States Dollar', 'icon': '₿', 'color': 'bg-orange-500'},
    {'symbol': 'ETH-USD', 'name': 'Ethereum / United States Dollar', 'icon': 'Ξ', 'color': 'bg-purple-500'},
]


def splash(request):
    return render(request, 'hermes/splash.html')


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


def load_credentials_from_json():
    """Load credentials from credentials.json file"""
    credentials_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'credentials.json')
    try:
        with open(credentials_path, 'r') as f:
            data = json.load(f)
            return data.get('credentials', [])
    except FileNotFoundError:
        logger.warning(f"credentials.json not found at {credentials_path}")
        return []
    except json.JSONDecodeError:
        logger.error(f"Invalid JSON in credentials.json")
        return []


@require_http_methods(["GET", "POST"])
def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        
        # Check credentials from JSON file
        json_credentials = load_credentials_from_json()
        valid_user = None
        
        for cred in json_credentials:
            if cred.get('username') == username and cred.get('password') == password:
                valid_user = cred
                break
        
        if valid_user:
            return JsonResponse({'success': True, 'message': 'Login successful'})
        else:
            return JsonResponse({'success': False, 'message': 'Invalid credentials'}, status=401)
    
    return render(request, 'hermes/login.html')
