from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from finance.uphold_api import UpholdAPIHandler
from finance.models import TradeHistory, BotConfig, PriceSnapshot
import logging
import json
import os
from datetime import datetime, timedelta
from django.utils import timezone

logger = logging.getLogger(__name__)

CURRENCIES = [
    {'symbol': 'EUR-USD', 'name': 'Euro / United States Dollar', 'icon': '€', 'color': 'bg-blue-500'},
    {'symbol': 'USD-EUR', 'name': 'United States Dollar / Euro', 'icon': '$', 'color': 'bg-green-500'},
    {'symbol': 'BTC-USD', 'name': 'Bitcoin / United States Dollar', 'icon': '₿', 'color': 'bg-orange-500'},
    {'symbol': 'ETH-USD', 'name': 'Ethereum / United States Dollar', 'icon': 'Ξ', 'color': 'bg-purple-500'},
]


def splash(request):
    return render(request, 'hermes/splash.html')


@login_required(login_url='/hermes/login/')
def home(request):
    api = UpholdAPIHandler()
    
    # Get current user
    current_user = request.user

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

    # Fetch recent trades for this user
    trades = TradeHistory.objects.filter(user=current_user).order_by('-timestamp')[:10]
    
    # Calculate total earnings and win rate from all trades for this user
    all_trades = TradeHistory.objects.filter(user=current_user)
    total_profit = 0
    winning_trades = 0
    total_trades = all_trades.count()
    
    for trade in all_trades:
        if hasattr(trade, 'profit') and trade.profit:
            try:
                profit_value = float(trade.profit)
                total_profit += profit_value
                if profit_value > 0:
                    winning_trades += 1
            except (ValueError, TypeError):
                pass
    
    # Calculate win rate percentage
    win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0

    # Fetch bot config
    try:
        config = BotConfig.get_config()
        risk_tolerance = config.risk_tolerance
        trade_size = config.trade_size_percentage
    except Exception:
        risk_tolerance = 0.5
        trade_size = 0.1
    
    # Calculate risk level based on actual closed trades (SELL operations)
    risk_level = 0
    sell_trades = all_trades.filter(operation="SELL")
    
    if sell_trades.count() > 0:
        # Calculate win rate from closed trades only
        # A profitable SELL is when price went up from the corresponding BUY
        # For simplicity: track the price of each SELL and compare to average buy price
        
        sell_count = sell_trades.count()
        
        # Get average buy price (all BUY trades)
        buy_trades = all_trades.filter(operation="BUY")
        if buy_trades.exists():
            buy_prices = [float(t.price_at_execution) for t in buy_trades]
            avg_buy_price = sum(buy_prices) / len(buy_prices) if buy_prices else 0
            
            # Count profitable sells (SELL price > avg buy price)
            profitable_sells = 0
            for sell in sell_trades:
                if float(sell.price_at_execution) > avg_buy_price:
                    profitable_sells += 1
            
            # Actual win rate of closed trades
            closed_win_rate = profitable_sells / sell_count if sell_count > 0 else 0
            loss_rate = 1 - closed_win_rate
            
            # Base risk from loss rate of closed positions
            base_risk = loss_rate * 100
        else:
            base_risk = 50  # No buy trades yet, neutral risk
        
        # Adjust based on trade size
        size_multiplier = 1 + (trade_size * 2)  # 1 to 3x multiplier
        
        # Calculate final risk
        risk_level = base_risk * size_multiplier
        risk_level = min(risk_level, 100)
    else:
        # No closed trades yet: use risk tolerance from config
        risk_level = risk_tolerance * 100

    context = {
        'top_currencies': top_currencies,
        'trades': trades,
        'risk_tolerance': risk_tolerance,
        'trade_size': trade_size,
        'total_earnings': f'{total_profit:,.2f}',
        'win_rate': f'{win_rate:.1f}',
        'total_trades': total_trades,
        'risk_level': f'{min(risk_level, 100):.1f}',
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
            # Get or create Django user
            from principal.models import User
            user, created = User.objects.get_or_create(
                username=username,
                defaults={'email': f'{username}@hermes.local'}
            )
            
            # Log the user in
            login(request, user)
            
            # Redirect to next page or home
            next_page = request.GET.get('next', '/home/')
            return redirect(next_page)
        else:
            # Return to login page with error
            return render(request, 'hermes/login.html', {
                'error': 'Invalid username or password'
            })
    
    return render(request, 'hermes/login.html')


def get_chart_data_by_range(time_range):
    """Get aggregated trade data for chart by time range"""
    now = timezone.now()
    
    # Determine date range
    if time_range == '1D':
        start_date = now - timedelta(days=1)
    elif time_range == '1W':
        start_date = now - timedelta(weeks=1)
    elif time_range == '1M':
        start_date = now - timedelta(days=30)
    elif time_range == '3M':
        start_date = now - timedelta(days=90)
    else:  # 'ALL'
        start_date = now - timedelta(days=365)
    
    # Get trades in range
    trades = TradeHistory.objects.filter(timestamp__gte=start_date).order_by('timestamp')
    
    # Aggregate data into buckets (max 12 data points)
    data_points = []
    if trades.exists():
        bucket_size = max(1, len(trades) // 12)
        cumulative_profit = 0
        
        for i, trade in enumerate(trades):
            try:
                profit = float(trade.price_at_execution) if hasattr(trade, 'price_at_execution') else 0
                cumulative_profit += profit
                
                if i % bucket_size == 0 or i == len(trades) - 1:
                    data_points.append({
                        'x': int((i / len(trades)) * 800),
                        'y': int(280 - (cumulative_profit % 280)),
                        'value': int(cumulative_profit),
                    })
            except (ValueError, TypeError):
                pass
    
    # Return default data points if empty
    if not data_points:
        data_points = [{'x': i * 72, 'y': 140 + (i % 2) * 20, 'value': 0} for i in range(12)]
    
    return data_points


@require_http_methods(["GET"])
def get_chart_data(request):
    """API endpoint to get chart data by time range"""
    time_range = request.GET.get('range', '1M')
    data = get_chart_data_by_range(time_range)
    return JsonResponse({'data': data})


# Global bot runner instance
_bot_runner = None

def get_bot_runner():
    """Get or create the global bot runner instance"""
    global _bot_runner
    if _bot_runner is None:
        from finance.bot_service import BotRunner
        _bot_runner = BotRunner()
    return _bot_runner


@csrf_exempt
@require_http_methods(["POST"])
def bot_start(request):
    """Start the trading bot"""
    try:
        runner = get_bot_runner()
        if not runner.is_running():
            runner.start()
            config = BotConfig.get_config()
            config.is_active = True
            config.save()
            return JsonResponse({'status': 'started', 'message': 'Bot started successfully'})
        else:
            return JsonResponse({'status': 'already_running', 'message': 'Bot is already running'})
    except Exception as e:
        logger.error(f"Error starting bot: {e}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def bot_stop(request):
    """Stop the trading bot"""
    try:
        runner = get_bot_runner()
        if runner.is_running():
            runner.stop()
            config = BotConfig.get_config()
            config.is_active = False
            config.save()
            return JsonResponse({'status': 'stopped', 'message': 'Bot stopped successfully'})
        else:
            return JsonResponse({'status': 'not_running', 'message': 'Bot is not running'})
    except Exception as e:
        logger.error(f"Error stopping bot: {e}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def bot_status(request):
    """Get bot status"""
    try:
        runner = get_bot_runner()
        config = BotConfig.get_config()
        return JsonResponse({
            'is_running': runner.is_running(),
            'is_active': config.is_active,
            'message': 'Bot is running' if runner.is_running() else 'Bot is stopped'
        })
    except Exception as e:
        logger.error(f"Error getting bot status: {e}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
