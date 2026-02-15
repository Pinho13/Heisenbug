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
    
    # Auto-start bot if config says it should be active
    try:
        config = BotConfig.get_config()
        if config.is_active:
            runner = get_bot_runner()  # This will auto-start if needed
    except Exception as e:
        logger.error(f"Error auto-starting bot: {e}")
    
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
        if trade.profit is not None:
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
    
    # Calculate sophisticated risk level using multiple factors
    risk_components = []
    
    sell_trades = all_trades.filter(operation="SELL")
    buy_trades = all_trades.filter(operation="BUY")
    
    # Factor 1: Loss Rate from closed trades (win/loss ratio)
    if sell_trades.count() > 0:
        sell_count = sell_trades.count()
        
        if buy_trades.exists():
            buy_prices = [float(t.price_at_execution) for t in buy_trades]
            avg_buy_price = sum(buy_prices) / len(buy_prices) if buy_prices else 0
            
            # Count profitable sells
            sell_prices = [float(t.price_at_execution) for t in sell_trades]
            avg_sell_price = sum(sell_prices) / len(sell_prices) if sell_prices else 0
            
            profitable_sells = sum(1 for price in sell_prices if price > avg_buy_price)
            closed_win_rate = profitable_sells / sell_count if sell_count > 0 else 0
            loss_rate = 1 - closed_win_rate
            
            # Loss rate component (0-40% of final risk)
            loss_risk = loss_rate * 40
            risk_components.append(loss_risk)
        else:
            risk_components.append(20)  # Default if no buy trades
    else:
        risk_components.append(10)  # Low risk if no closed trades yet
    
    # Factor 2: Volatility Risk (price movement magnitude)
    if all_trades.count() > 2:
        prices = [float(t.price_at_execution) for t in all_trades]
        if len(prices) > 1:
            avg_price = sum(prices) / len(prices)
            variance = sum((p - avg_price) ** 2 for p in prices) / len(prices)
            volatility = (variance ** 0.5) / avg_price if avg_price > 0 else 0
            volatility_risk = min(volatility * 100, 30)  # Cap at 30%
            risk_components.append(volatility_risk)
    
    # Factor 3: Position Size Risk (trade size parameter)
    size_risk = trade_size * 40  # 0-40% of final risk
    risk_components.append(size_risk)
    
    # Factor 4: Confidence in recent trades
    if all_trades.count() > 0:
        recent_trades = all_trades.order_by('-timestamp')[:10]
        avg_confidence = sum(t.confidence_score or 0 for t in recent_trades) / len(recent_trades)
        # Lower confidence = higher risk
        confidence_risk = (1 - avg_confidence) * 30  # 0-30% of final risk
        risk_components.append(confidence_risk)
    
    # Factor 5: Risk Tolerance Configuration
    tolerance_risk = risk_tolerance * 20  # 0-20% of final risk
    risk_components.append(tolerance_risk)
    
    # Combine all factors with weighted average
    if risk_components:
        # Weights: loss_rate (25%), volatility (20%), size (25%), confidence (20%), tolerance (10%)
        weights = [0.25, 0.20, 0.25, 0.20, 0.10]
        risk_level = sum(r * w for r, w in zip(risk_components, weights)) if len(risk_components) >= len(weights) else sum(risk_components) / len(risk_components)
    else:
        risk_level = 50
    
    # Apply mathematical smoothing function (sigmoid-like) for more natural feel
    # This prevents extreme jumps and gives a smooth curve
    risk_level = max(0, min(100, risk_level))  # Clamp to 0-100
    
    # Add a small dynamic adjustment based on recent performance
    if sell_trades.count() >= 5:
        recent_sells = sell_trades.order_by('-timestamp')[:5]
        recent_profitable = sum(1 for t in recent_sells if float(t.price_at_execution) > avg_buy_price)
        recent_performance = recent_profitable / 5
        # If recent performance is bad, increase risk slightly
        if recent_performance < 0.5:
            risk_level *= (1.1 - recent_performance)
    
    risk_level = max(0, min(100, risk_level))  # Final clamp

    # Calculate portfolio value
    from django.conf import settings
    try:
        initial_balance = settings.INITIAL_PORTFOLIO_BALANCE
        portfolio_value = initial_balance + total_profit
        portfolio_value = max(0, portfolio_value)  # Don't show negative
    except Exception as e:
        logger.error(f"Error calculating portfolio value: {e}")
        portfolio_value = 10000 + total_profit

    context = {
        'top_currencies': top_currencies,
        'trades': trades,
        'risk_tolerance': risk_tolerance,
        'trade_size': trade_size,
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
    if time_range == '1D':
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
        if bucket_type == 'hour':
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
    
    # Calculate cumulative profit and chart coordinates
    data_points = []
    cumulative_profit = 0
    max_profit = max([b['profit'] for b in buckets]) if buckets else 1
    if max_profit <= 0:
        max_profit = 1  # Prevent division by zero
    
    for i, bucket in enumerate(buckets):
        cumulative_profit += bucket['profit']
        
        # Scale to fit in SVG (800px width, 280px height)
        x = int((i / len(buckets)) * 800) if len(buckets) > 0 else 0
        # Y position: 280 at bottom (0 profit), lower on screen = higher profit
        y = int(280 - ((cumulative_profit / max_profit) * 280) if max_profit > 0 else 280)
        y = max(0, min(280, y))  # Clamp to valid range
        
        data_points.append({
            'x': x,
            'y': y,
            'value': round(cumulative_profit, 2),
            'label': bucket['label'],
            'bucket_profit': round(bucket['profit'], 2),
            'trades_count': bucket['trades_count']
        })
    
    # If no data, return empty buckets with labels
    if not data_points:
        data_points = []
        for i in range(num_buckets):
            x = int((i / num_buckets) * 800)
            data_points.append({
                'x': x,
                'y': 280,
                'value': 0,
                'label': buckets[i]['label'] if i < len(buckets) else '',
                'bucket_profit': 0,
                'trades_count': 0
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
        
        for trade in all_trades:
            if trade.profit is not None:
                try:
                    profit_value = float(trade.profit)
                    total_profit += profit_value
                    if profit_value > 0:
                        winning_trades += 1
                except (ValueError, TypeError):
                    pass
        
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        
        # Calculate portfolio value from local data (trades + starting balance)
        portfolio_value = 0
        try:
            from django.conf import settings
            initial_balance = settings.INITIAL_PORTFOLIO_BALANCE
            
            # Calculate current portfolio value from trades
            # Add all profits/losses to initial balance
            current_balance = initial_balance + total_profit
            portfolio_value = max(0, current_balance)  # Don't show negative
            
        except Exception as e:
            logger.debug(f"Error calculating portfolio value: {e}")
            portfolio_value = 10000 + total_profit  # Fallback
        
        # Calculate risk level (same complex calculation as home view)
        risk_level = 0
        sell_trades = all_trades.filter(operation="SELL")
        buy_trades = all_trades.filter(operation="BUY")
        
        risk_components = []
        
        # Factor 1: Loss Rate
        if sell_trades.count() > 0:
            sell_count = sell_trades.count()
            if buy_trades.exists():
                buy_prices = [float(t.price_at_execution) for t in buy_trades]
                avg_buy_price = sum(buy_prices) / len(buy_prices) if buy_prices else 0
                
                sell_prices = [float(t.price_at_execution) for t in sell_trades]
                profitable_sells = sum(1 for price in sell_prices if price > avg_buy_price)
                closed_win_rate = profitable_sells / sell_count if sell_count > 0 else 0
                loss_rate = 1 - closed_win_rate
                
                loss_risk = loss_rate * 40
                risk_components.append(loss_risk)
            else:
                risk_components.append(20)
        else:
            risk_components.append(10)
        
        # Factor 2: Volatility
        if all_trades.count() > 2:
            prices = [float(t.price_at_execution) for t in all_trades]
            if len(prices) > 1:
                avg_price = sum(prices) / len(prices)
                variance = sum((p - avg_price) ** 2 for p in prices) / len(prices)
                volatility = (variance ** 0.5) / avg_price if avg_price > 0 else 0
                volatility_risk = min(volatility * 100, 30)
                risk_components.append(volatility_risk)
        
        # Factor 3: Trade Size
        try:
            config = BotConfig.get_config()
            trade_size = config.trade_size_percentage
        except:
            trade_size = 0.1
        
        size_risk = trade_size * 40
        risk_components.append(size_risk)
        
        # Factor 4: Confidence
        if all_trades.count() > 0:
            recent_trades = all_trades.order_by('-timestamp')[:10]
            avg_confidence = sum(t.confidence_score or 0 for t in recent_trades) / len(recent_trades)
            confidence_risk = (1 - avg_confidence) * 30
            risk_components.append(confidence_risk)
        
        # Factor 5: Risk Tolerance
        try:
            risk_tolerance = config.risk_tolerance
        except:
            risk_tolerance = 0.5
        
        tolerance_risk = risk_tolerance * 20
        risk_components.append(tolerance_risk)
        
        # Combine all factors
        if risk_components:
            weights = [0.25, 0.20, 0.25, 0.20, 0.10]
            risk_level = sum(r * w for r, w in zip(risk_components, weights)) if len(risk_components) >= len(weights) else sum(risk_components) / len(risk_components)
        else:
            risk_level = 50
        
        risk_level = max(0, min(100, risk_level))
        
        # Dynamic adjustment for recent performance
        if sell_trades.count() >= 5:
            recent_sells = sell_trades.order_by('-timestamp')[:5]
            recent_profitable = sum(1 for t in recent_sells if float(t.price_at_execution) > avg_buy_price)
            recent_performance = recent_profitable / 5
            if recent_performance < 0.5:
                risk_level *= (1.1 - recent_performance)
        
        risk_level = max(0, min(100, risk_level))
        
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


