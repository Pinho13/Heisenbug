from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Sum
from finance.models import TradeHistory, BotConfig, PriceSnapshot, UserBalance
import logging
import json
import os
import math
from datetime import datetime, timedelta
from django.utils import timezone

logger = logging.getLogger(__name__)


def calculate_risk_level(all_trades, config):
    """Shared risk calculation used by both the home view and the metrics API.

    Always produces exactly 5 weighted factors so the result responds to
    every input (investment amount, trade history, config) instead of
    falling back to a flat average.
    """
    sell_trades = all_trades.filter(operation="SELL")
    buy_trades = all_trades.filter(operation="BUY")

    trade_size = config.trade_size_percentage or 0.1
    risk_tolerance = config.risk_tolerance or 0.5
    investment_amount = float(config.investment_amount or 0)

    # --- Factor 1: Loss rate (0-40) ---
    if sell_trades.count() > 0 and buy_trades.exists():
        buy_prices = [float(t.price_at_execution) for t in buy_trades]
        avg_buy_price = sum(buy_prices) / len(buy_prices)
        sell_prices = [float(t.price_at_execution) for t in sell_trades]
        profitable_sells = sum(1 for p in sell_prices if p > avg_buy_price)
        loss_rate = 1 - (profitable_sells / sell_trades.count())
        loss_risk = loss_rate * 40
    elif sell_trades.count() > 0:
        loss_risk = 25
    else:
        loss_risk = 18

    # --- Factor 2: Volatility (0-30) ---
    if all_trades.count() > 2:
        prices = [float(t.price_at_execution) for t in all_trades]
        avg_price = sum(prices) / len(prices)
        variance = sum((p - avg_price) ** 2 for p in prices) / len(prices)
        volatility = (variance ** 0.5) / avg_price if avg_price > 0 else 0
        volatility_risk = min(volatility * 100, 30)
    else:
        volatility_risk = 12  # baseline when few trades

    # --- Factor 3: Investment exposure (0-40) ---
    # Combines investment amount with trade-size to reflect actual money at risk.
    exposure = investment_amount * trade_size  # money risked per trade
    if exposure > 0:
        investment_risk = min(math.log10(exposure + 1) * 10, 40)
    else:
        investment_risk = 0

    # --- Factor 4: Confidence (0-30) ---
    if all_trades.count() > 0:
        recent = all_trades.order_by('-timestamp')[:10]
        avg_conf = sum(t.confidence_score or 0 for t in recent) / len(recent)
        confidence_risk = (1 - avg_conf) * 30
    else:
        confidence_risk = 20  # neutral baseline instead of skipping

    # --- Factor 5: Risk tolerance config (0-20) ---
    tolerance_risk = risk_tolerance * 20

    # Weighted combination (weights sum to 1.0)
    weights = [0.20, 0.15, 0.25, 0.20, 0.20]
    components = [loss_risk, volatility_risk, investment_risk, confidence_risk, tolerance_risk]
    risk_level = sum(c * w for c, w in zip(components, weights))

    # Dynamic adjustment for recent sell performance
    if sell_trades.count() >= 5 and buy_trades.exists():
        buy_prices = [float(t.price_at_execution) for t in buy_trades]
        avg_buy_price = sum(buy_prices) / len(buy_prices)
        recent_sells = sell_trades.order_by('-timestamp')[:5]
        recent_profitable = sum(1 for t in recent_sells if float(t.price_at_execution) > avg_buy_price)
        recent_performance = recent_profitable / 5
        if recent_performance < 0.5:
            risk_level *= (1.1 - recent_performance)

    return max(0, min(100, risk_level))

CURRENCIES = [
    {'symbol': 'BTC-EUR', 'name': 'Bitcoin / Euro', 'icon': '₿', 'color': 'bg-orange-500'},
    {'symbol': 'ETH-EUR', 'name': 'Ethereum / Euro', 'icon': 'Ξ', 'color': 'bg-purple-500'},
    {'symbol': 'EUR-USD', 'name': 'Euro / United States Dollar', 'icon': '€', 'color': 'bg-blue-500'},
    {'symbol': 'BTC-USD', 'name': 'Bitcoin / United States Dollar', 'icon': '₿', 'color': 'bg-yellow-500'},
    {'symbol': 'ETH-USD', 'name': 'Ethereum / United States Dollar', 'icon': 'Ξ', 'color': 'bg-indigo-500'},
    {'symbol': 'USD-EUR', 'name': 'United States Dollar / Euro', 'icon': '$', 'color': 'bg-green-500'},
]


def splash(request):
    return render(request, 'hermes/splash.html')


@login_required(login_url='/hermes/login/')
def home(request):
    # Auto-start bot if config says it should be active
    try:
        config = BotConfig.get_config()
        if config.is_active:
            runner = get_bot_runner()  # This will auto-start if needed
    except Exception as e:
        logger.error(f"Error auto-starting bot: {e}")
    
    # Get current user
    current_user = request.user

    # Load market rates from cached PriceSnapshot data (populated by bot)
    # This avoids blocking the page on slow/unreachable external API calls
    top_currencies = []
    for currency in CURRENCIES:
        try:
            snapshot = PriceSnapshot.objects.filter(pair=currency['symbol']).order_by('-timestamp').first()
            if snapshot:
                bid = float(snapshot.bid)
                ask = float(snapshot.ask)
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
            logger.error(f"Error loading cached price for {currency['symbol']}: {e}")

    # Fetch recent trades for this user
    trades = TradeHistory.objects.filter(user=current_user).order_by('-timestamp')[:10]
    
    # Calculate total earnings and win rate from all trades for this user
    all_trades = TradeHistory.objects.filter(user=current_user)
    total_profit = 0
    winning_trades = 0
    # Each round-trip is 2 trades (BUY+SELL), so count completed pairs
    total_trades = all_trades.count()
    round_trips = total_trades // 2

    for trade in all_trades:
        if trade.profit is not None:
            try:
                profit_value = float(trade.profit)
                total_profit += profit_value
                if profit_value > 0:
                    winning_trades += 1
            except (ValueError, TypeError):
                pass

    # Win rate based on round-trips, not individual trades
    win_rate = (winning_trades / round_trips * 100) if round_trips > 0 else 0

    # Fetch bot config
    try:
        config = BotConfig.get_config()
    except Exception:
        config = BotConfig()

    risk_level = calculate_risk_level(all_trades, config)

    # Portfolio value = sum of all UserBalance amounts (the real source of truth)
    portfolio_value = float(
        UserBalance.objects.filter(user=current_user)
        .aggregate(total=Sum('amount'))['total'] or 0
    )

    context = {
        'top_currencies': top_currencies,
        'trades': trades,
        'total_earnings': f'{total_profit:,.2f}',
        'win_rate': f'{win_rate:.1f}',
        'total_trades': total_trades,
        'risk_level': f'{min(risk_level, 100):.1f}',
        'portfolio_value': f'{portfolio_value:,.2f}',
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


def get_chart_data_by_range(time_range, user_id=None):
    """Get aggregated trade data for chart by time range"""
    now = timezone.now()
    
    # Determine date range and bucket strategy
    if time_range == '30M':
        start_date = now - timedelta(minutes=30)
        bucket_type = 'minute'
        num_buckets = 30
    elif time_range == '1D':
        start_date = now - timedelta(days=1)
        bucket_type = 'hour'
        num_buckets = 24
    elif time_range == '1W':
        start_date = now - timedelta(weeks=1)
        bucket_type = 'day'
        num_buckets = 7
    elif time_range == '1M':
        start_date = now - timedelta(days=30)
        bucket_type = 'day'
        num_buckets = 30
    elif time_range == '3M':
        start_date = now - timedelta(days=90)
        bucket_type = 'week'
        num_buckets = 13
    else:  # 'ALL' or '1Y'
        start_date = now - timedelta(days=365)
        bucket_type = 'month'
        num_buckets = 12
    
    # Get trades in range (use profit field)
    query = TradeHistory.objects.filter(timestamp__gte=start_date)
    if user_id:
        query = query.filter(user_id=user_id)
    trades = query.order_by('timestamp')
    
    # Create buckets with labels
    from datetime import datetime
    buckets = []
    current_date = start_date
    
    for i in range(num_buckets):
        if bucket_type == 'minute':
            bucket_end = current_date + timedelta(minutes=1)
            label = current_date.strftime('%H:%M')
        elif bucket_type == 'hour':
            bucket_end = current_date + timedelta(hours=1)
            label = current_date.strftime('%H:%M')
        elif bucket_type == 'day':
            bucket_end = current_date + timedelta(days=1)
            label = current_date.strftime('%d')
        elif bucket_type == 'week':
            bucket_end = current_date + timedelta(weeks=1)
            label = f"W{current_date.strftime('%U')}"
        else:  # month
            if current_date.month == 12:
                bucket_end = current_date.replace(year=current_date.year+1, month=1)
            else:
                bucket_end = current_date.replace(month=current_date.month+1)
            label = current_date.strftime('%b')
        
        # Sum profits in this bucket
        bucket_trades = trades.filter(timestamp__gte=current_date, timestamp__lt=bucket_end)
        bucket_profit = sum(float(t.profit) if t.profit else 0 for t in bucket_trades)
        
        buckets.append({
            'label': label,
            'profit': bucket_profit,
            'trades_count': bucket_trades.count()
        })
        
        current_date = bucket_end
    
    # First pass: compute cumulative profits to find the true max for Y scaling
    cumulative_values = []
    running = 0
    for bucket in buckets:
        running += bucket['profit']
        cumulative_values.append(running)

    # Use the max absolute cumulative value for scaling (handles both positive and negative)
    max_abs = max((abs(v) for v in cumulative_values), default=1)
    if max_abs <= 0:
        max_abs = 1

    # Second pass: build data points with correct Y coordinates
    data_points = []
    for i, bucket in enumerate(buckets):
        cumulative = cumulative_values[i]

        # X: evenly spaced across 800px width
        x = int((i / max(len(buckets) - 1, 1)) * 800)
        # Y: 280 = bottom (0 profit), 0 = top (max profit)
        y = int(280 - (cumulative / max_abs) * 250)
        y = max(10, min(280, y))

        data_points.append({
            'x': x,
            'y': y,
            'value': round(cumulative, 2),
            'label': bucket['label'],
            'bucket_profit': round(bucket['profit'], 2),
            'trades_count': bucket['trades_count'],
        })

    return data_points


@require_http_methods(["GET"])
def get_chart_data(request):
    """API endpoint to get chart data by time range"""
    time_range = request.GET.get('range', '1M')
    user_id = request.user.id if request.user.is_authenticated else None
    data = get_chart_data_by_range(time_range, user_id)
    return JsonResponse({'data': data})


# Keep track of the current bot runner in this module
_bot_runner = None

def get_bot_runner():
    """Get or create the global bot runner instance"""
    global _bot_runner
    if _bot_runner is None:
        from finance.bot_service import BotRunner
        _bot_runner = BotRunner()
    
    # If bot config says it should be active but runner isn't running, start it
    try:
        config = BotConfig.get_config()
        if config.is_active and not _bot_runner.is_running():
            logger.info("Bot should be active but isn't running, starting...")
            _bot_runner.start()
    except Exception as e:
        logger.error(f"Error auto-starting bot: {e}")
    
    return _bot_runner


@csrf_exempt
@require_http_methods(["POST"])
def bot_start(request):
    """Start the trading bot"""
    try:
        config = BotConfig.get_config()

        # Set the bot user to the currently logged-in user
        if request.user.is_authenticated:
            config.bot_user = request.user
            config.save()

        # Seed initial balance from investment amount if user has no balances
        if request.user.is_authenticated and config.investment_amount > 0:
            from decimal import Decimal
            existing = UserBalance.objects.filter(user=request.user)
            if not existing.exists():
                UserBalance.objects.create(
                    user=request.user,
                    currency='EUR',
                    amount=Decimal(str(config.investment_amount))
                )
                logger.info(f"Created initial EUR balance of {config.investment_amount} for {request.user}")

        # Update config
        config.is_active = True
        config.save()

        # Try to start bot runner
        runner = get_bot_runner()
        if not runner.is_running():
            runner.start()
        
        return JsonResponse({
            'status': 'started',
            'message': 'Bot started successfully',
            'is_running': runner.is_running(),
            'is_active': config.is_active
        })
    except Exception as e:
        logger.error(f"Error starting bot: {e}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def bot_stop(request):
    """Stop the trading bot"""
    try:
        config = BotConfig.get_config()
        
        # Update config
        config.is_active = False
        config.save()
        
        # Try to stop bot runner
        runner = get_bot_runner()
        if runner.is_running():
            runner.stop()
        
        return JsonResponse({
            'status': 'stopped',
            'message': 'Bot stopped successfully',
            'is_running': runner.is_running(),
            'is_active': config.is_active
        })
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


@login_required(login_url='/hermes/login/')
@require_http_methods(["GET"])
def get_recent_trades(request):
    """Get recent trades for current user as JSON"""
    try:
        current_user = request.user
        trades = TradeHistory.objects.filter(user=current_user).order_by('-timestamp')[:10]
        
        trades_data = []
        for trade in trades:
            trades_data.append({
                'time': trade.timestamp.strftime('%H:%M:%S'),
                'pair': trade.pair,
                'operation': trade.operation,
                'amount': str(trade.amount),
                'price': str(trade.price_at_execution),
                'status': trade.status
            })
        
        return JsonResponse({
            'trades': trades_data,
            'count': len(trades_data)
        })
    except Exception as e:
        logger.error(f"Error fetching trades: {e}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@login_required(login_url='/hermes/login/')
@require_http_methods(["GET"])
def get_dashboard_metrics(request):
    """Get all dashboard metrics for real-time updates"""
    try:
        current_user = request.user
        all_trades = TradeHistory.objects.filter(user=current_user)
        
        # Calculate earnings
        total_profit = 0
        winning_trades = 0
        total_trades = all_trades.count()
        round_trips = total_trades // 2

        for trade in all_trades:
            if trade.profit is not None:
                try:
                    profit_value = float(trade.profit)
                    total_profit += profit_value
                    if profit_value > 0:
                        winning_trades += 1
                except (ValueError, TypeError):
                    pass

        win_rate = (winning_trades / round_trips * 100) if round_trips > 0 else 0
        
        # Portfolio value = sum of all UserBalance amounts (the real source of truth)
        portfolio_value = float(
            UserBalance.objects.filter(user=current_user)
            .aggregate(total=Sum('amount'))['total'] or 0
        )
        
        config = BotConfig.get_config()
        risk_level = calculate_risk_level(all_trades, config)
        
        return JsonResponse({
            'risk_level': f'{risk_level:.1f}',
            'earnings': f'{total_profit:,.2f}',
            'win_rate': f'{win_rate:.1f}',
            'total_trades': total_trades,
            'winning_trades': winning_trades,
            'portfolio_value': f'{portfolio_value:,.2f}'
        })
    except Exception as e:
        logger.error(f"Error fetching metrics: {e}", exc_info=True)
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@csrf_exempt
@login_required(login_url='/hermes/login/')
@require_http_methods(["GET", "POST"])
def user_preferences(request):
    """Get or save user trading preferences (selected currencies + investment amount)"""
    try:
        config = BotConfig.get_config()

        if request.method == 'GET':
            currencies = [c.strip() for c in config.selected_currencies.split(',') if c.strip()]
            return JsonResponse({
                'selected_currencies': currencies,
                'investment_amount': str(config.investment_amount),
            })

        # POST
        data = json.loads(request.body)
        if 'selected_currencies' in data:
            currencies = data['selected_currencies']
            if isinstance(currencies, list):
                config.selected_currencies = ','.join(currencies)
        if 'investment_amount' in data:
            try:
                new_amount = float(data['investment_amount'])
                config.investment_amount = new_amount
                # Update initial balance if no trades have been made yet
                if request.user.is_authenticated and new_amount > 0:
                    from decimal import Decimal
                    has_trades = TradeHistory.objects.filter(user=request.user).exists()
                    if not has_trades:
                        UserBalance.objects.update_or_create(
                            user=request.user, currency='EUR',
                            defaults={'amount': Decimal(str(new_amount))}
                        )
            except (ValueError, TypeError):
                pass
        config.save()

        return JsonResponse({'status': 'ok'})
    except Exception as e:
        logger.error(f"Error in user_preferences: {e}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

