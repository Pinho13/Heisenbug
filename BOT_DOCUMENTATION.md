# Trading Bot Documentation

## Overview

The advanced trading bot analyzes available trading pairs from your portfolio and automatically recommends and executes trades to maximize holdings. It uses a sophisticated risk analysis engine to ensure only safe, high-confidence trades are executed.

## Architecture

### Components

1. **UpholdAPIHandler** - API integration with caching and retry logic
2. **MarketDataCache** - Price caching with TTL for efficient data fetching
3. **RiskAnalyzer** - Calculates volatility and risk scores
4. **PortfolioOptimizer** - Generates and ranks trade opportunities
5. **AdvancedTradeBot** - Main bot execution engine
6. **BotRunner** - Manages bot lifecycle in background thread
7. **BotStatusConsumer** - WebSocket consumer for real-time frontend updates

### Data Flow

```
User Config (Admin/WebSocket)
    ↓
BotConfig Model (Django DB)
    ↓
BotRunner.run_iteration()
    ├─ Fetch Prices (API + Cache)
    ├─ Get Portfolio (Uphold API)
    ├─ PortfolioOptimizer.find_best_trade()
    │  ├─ Generate trade opportunities
    │  ├─ RiskAnalyzer scores each
    │  └─ Filter by risk/confidence
    ├─ Execute best trade
    ├─ Store in TradeHistory
    └─ Broadcast via WebSocket → Frontend
```

## Configuration

### Via Admin Panel

1. Go to `http://localhost:8000/admin/`
2. Click on "Bot Config"
3. Set:
   - **is_active**: Enable/disable bot
   - **risk_tolerance**: 0.0 (conservative) to 1.0 (aggressive)
   - **min_confidence_score**: Minimum confidence for trade execution (0.0-1.0)
   - **trade_size_amount**: Fixed amount per trade (optional)
   - **trade_size_percentage**: Percentage of holdings to trade (0.01-1.0)
   - **check_interval_seconds**: How often to check for trades (1-300s)
   - **cache_ttl_seconds**: Price cache duration (1-60s)

### Via WebSocket

Send JSON to `ws://localhost:8000/ws/bot/status/`:

```json
{
  "action": "update_config",
  "data": {
    "is_active": true,
    "risk_tolerance": 0.6,
    "min_confidence": 0.7,
    "check_interval": 5,
    "cache_ttl": 3
  }
}
```

## Trading Pairs

### Add Trading Pairs

**Via Admin:**
1. Go to Admin → "Trading Pairs"
2. Click "Add Trading Pair"
3. Enter pair symbol (e.g., "BTC-USD")
4. Set priority (higher = monitored more frequently)
5. Enable the pair

**Via Management Command:**
```bash
python manage.py runbot --add-pair BTC-USD
python manage.py runbot --add-pair ETH-USD
```

**Via Django Shell:**
```python
from finance.models import TradingPair
TradingPair.objects.create(pair_symbol="BTC-USD", priority=100, is_enabled=True)
TradingPair.objects.create(pair_symbol="ETH-USD", priority=90, is_enabled=True)
```

## Running the Bot

### Start Bot with Django Management Command

```bash
# Basic start
python manage.py runbot

# With custom settings
python manage.py runbot --risk-level 0.7 --min-confidence 0.75 --interval 3

# Dry-run mode (test without executing trades)
python manage.py runbot --dry-run

# Add trading pairs on startup
python manage.py runbot --add-pair BTC-USD --add-pair ETH-USD
```

### Start with Daphne (For WebSocket Support)

```bash
daphne -b 0.0.0.0 -p 8000 core.asgi:application
```

Then run bot in separate terminal:
```bash
python manage.py runbot
```

## API Reference

### WebSocket Messages

#### Connect
```json
{
  "type": "connection",
  "message": "Connected to bot status stream"
}
```

#### Request Bot Status
**Send:**
```json
{"action": "get_status"}
```

**Receive:**
```json
{
  "type": "bot_status",
  "data": {
    "is_active": true,
    "risk_tolerance": 0.5,
    "min_confidence": 0.7,
    "check_interval": 5,
    "cache_ttl": 3,
    "recent_trades": [...]
  }
}
```

#### Request Recent Trades
**Send:**
```json
{"action": "get_recent_trades", "limit": 10}
```

**Receive:**
```json
{
  "type": "recent_trades",
  "data": [
    {
      "id": 1,
      "from_pair": "BTC",
      "to_pair": "USD",
      "decision": "BUY",
      "status": "EXECUTED",
      "confidence": 0.85,
      "risk": 0.3,
      "volatility": 0.02,
      "created_at": "2026-02-14T02:30:00Z",
      ...
    }
  ]
}
```

#### Update Configuration
**Send:**
```json
{
  "action": "update_config",
  "data": {
    "is_active": true,
    "risk_tolerance": 0.6
  }
}
```

**Receive:**
```json
{
  "type": "config_updated",
  "message": "Configuration updated successfully",
  "data": {...}
}
```

#### Trade Execution Notification
**Broadcast (when trade executed):**
```json
{
  "type": "trade_executed",
  "data": {
    "from_pair": "BTC",
    "to_pair": "USD",
    "amount": 0.5,
    "confidence": 0.85,
    "risk": 0.3,
    "expected_return": "0.025"
  },
  "timestamp": "2026-02-14T02:30:00Z"
}
```

#### Price Updates
**Broadcast (periodic):**
```json
{
  "type": "price_update",
  "pair": "BTC-USD",
  "data": {
    "bid": "45000.00",
    "ask": "45100.00",
    "last": "45050.00",
    "timestamp": "2026-02-14T02:30:00Z"
  }
}
```

## Risk Management

### Risk Score Calculation

```
Risk Score = Volatility / (Confidence × Potential_Gain)
```

- **Volatility**: Calculated from recent price movements (0-1)
- **Confidence**: Based on expected return and volatility (0-1)
- **Potential Gain**: Expected profit percentage

### Trade Decision Logic

A trade is executed if:
1. `confidence_score >= min_confidence_score`
2. `risk_score <= risk_tolerance`
3. `expected_return > 0.1%`

### Example Scenarios

**Conservative (risk_tolerance=0.3):**
- Only low-volatility trades
- High minimum confidence required
- Fewer trades, but safer

**Aggressive (risk_tolerance=0.9):**
- Accepts higher volatility
- Lower confidence threshold
- More frequent trades

## Database Cleanup

### Trade History Retention

- Maximum 100 trades kept in database
- Older trades automatically deleted
- Cleanup runs after each executed trade
- Prevents database bloat

### Manual Cleanup

```python
from finance.models import TradeHistory

# Keep last 50 trades, delete older
TradeHistory.cleanup_old_trades(keep_count=50)

# Delete all trades (careful!)
TradeHistory.objects.all().delete()
```

## Performance Tuning

### Cache TTL

- **Lower (1-2s)**: More fresh data, more API calls
- **Higher (5-10s)**: Fewer API calls, slightly stale data
- Recommendation: **3-5 seconds**

### Check Interval

- **Lower (1-2s)**: More frequent checks, higher CPU/API load
- **Higher (10-30s)**: Less frequent, may miss opportunities
- Recommendation: **3-5 seconds**

### Trade Size

- **Fixed Amount**: Consistent trade size
- **Percentage**: Scales with portfolio (recommended)
- Recommendation: **10% of holdings per trade**

## Monitoring & Debugging

### View Bot Logs

```bash
# Django debug mode
python manage.py runbot  # Shows INFO/ERROR logs

# Enable debug logging
export DJANGO_LOG_LEVEL=DEBUG
python manage.py runbot
```

### Check Recent Trades

```bash
# Via Django shell
python manage.py shell

from finance.models import TradeHistory
trades = TradeHistory.objects.all()[:10]
for t in trades:
    print(f"{t.from_pair}→{t.to_pair}: {t.confidence:.2f} confidence, {t.status}")
```

### Monitor via Admin

1. Go to Admin → Trade History
2. Filter by status (EXECUTED/FAILED/PENDING)
3. View decision reasoning and results

### Health Check

```python
from finance.models import BotConfig, TradingPair

# Check config
config = BotConfig.get_config()
print(f"Bot Active: {config.is_active}")

# Check pairs
pairs = TradingPair.objects.filter(is_enabled=True)
print(f"Monitoring {pairs.count()} pairs")

# Check recent trades
from finance.models import TradeHistory
recent = TradeHistory.objects.all()[:1]
print(f"Last trade: {recent[0] if recent else 'None'}")
```

## Troubleshooting

### Bot Not Making Trades

1. Check if bot is active: `BotConfig.is_active = True`
2. Verify trading pairs are enabled: `TradingPair.objects.filter(is_enabled=True).exists()`
3. Check minimum confidence isn't too high
4. Verify API connection working
5. Check logs for errors

### High API Rate Limiting

- Increase `cache_ttl_seconds`
- Increase `check_interval_seconds`
- Reduce number of enabled trading pairs

### WebSocket Not Connecting

1. Ensure running with Daphne: `daphne core.asgi:application`
2. Check firewall allows WebSocket (port 8000)
3. Verify client connecting to `ws://` not `http://`
4. Check browser console for errors

### Memory Usage Growing

1. Reduce `volatility_window` in `RiskAnalyzer` (default 10)
2. Ensure trade history cleanup running
3. Monitor price snapshot table size
4. Clear old price snapshots if needed

## Integration with Frontend

### Expected Endpoints

- **WebSocket**: `ws://localhost:8000/ws/bot/status/`
- **REST**: Admin panel at `http://localhost:8000/admin/`
- **Django Shell**: `python manage.py shell`

### Frontend Should Display

1. Real-time trade execution notifications
2. Current bot status (active/inactive)
3. Recent trades with confidence/risk scores
4. Current portfolio holdings
5. Configuration panel
6. Price updates

### Example Frontend Connection

```javascript
const ws = new WebSocket('ws://localhost:8000/ws/bot/status/');

ws.onmessage = function(event) {
  const data = JSON.parse(event.data);
  
  if (data.type === 'trade_executed') {
    console.log('Trade executed:', data.data);
    updateUI(data.data);
  } else if (data.type === 'price_update') {
    console.log('Price update:', data.pair, data.data);
  }
};

ws.onopen = function(event) {
  // Request current status
  ws.send(JSON.stringify({action: 'get_status'}));
};
```

## Advanced Configuration

### Custom Risk Tolerance

Edit `BotConfig.risk_tolerance` from 0.0 to 1.0:
- `0.0-0.3`: Very conservative
- `0.3-0.6`: Moderate
- `0.6-0.9`: Aggressive
- `0.9-1.0`: Very aggressive

### Custom Trade Size

Set either:
1. `BotConfig.trade_size_amount` for fixed amount (e.g., 0.1 BTC)
2. `BotConfig.trade_size_percentage` for % of holdings (e.g., 0.1 = 10%)

### Multiple Bots

Run multiple bot instances with different configs:
```bash
python manage.py runbot --risk-level 0.3 &
python manage.py runbot --risk-level 0.7 &
```

## Best Practices

1. **Start Conservative**: Begin with low risk tolerance, increase gradually
2. **Monitor Actively**: Watch trades for first few hours
3. **Test Dry Run**: Use `--dry-run` flag before live trading
4. **Diversify Pairs**: Monitor multiple trading pairs
5. **Set Limits**: Use appropriate trade sizes
6. **Review Logs**: Check trade reasoning regularly
7. **Adjust Intervals**: Balance between fresh data and API load
8. **Keep History**: Don't delete trade history, use cleanup limits

## Support & Issues

For issues or questions:
1. Check logs: `python manage.py runbot`
2. Review trade history in admin
3. Verify configuration in BotConfig
4. Test with smaller amounts first
5. Enable debug logging for detailed output

