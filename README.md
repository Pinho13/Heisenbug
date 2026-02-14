# Heisenbug
## 2026 BUGSBYTE PROJECT

## Advanced Trading Bot

An intelligent trading bot that analyzes cryptocurrency and currency pairs, calculates risk, and automatically executes profitable trades to maximize your holdings.

### Features

✅ **Real-Time Market Analysis** - Monitors multiple trading pairs simultaneously  
✅ **Risk Assessment** - Calculates volatility and risk scores before trading  
✅ **Portfolio Optimization** - Evaluates all possible trades and recommends the best  
✅ **Confidence-Based Execution** - Only executes high-confidence, low-risk trades  
✅ **WebSocket Real-Time Updates** - Live trade notifications and price updates  
✅ **Database History** - Automatic cleanup keeps last 100 trades  
✅ **Admin Control Panel** - Full Django admin for configuration  
✅ **Configurable Strategy** - Adjust risk tolerance, trade size, intervals  

### Quick Start

#### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

#### 2. Run Migrations
```bash
python manage.py migrate
```

#### 3. Start the Bot
```bash
python manage.py runbot --risk-level 0.5 --add-pair BTC-USD --add-pair ETH-USD
```

#### 4. Monitor via Admin
```bash
python manage.py createsuperuser
python manage.py runserver
# Visit http://localhost:8000/admin/
```

### Architecture

**Core Components:**
- `finance/bot_service.py` - Main bot engine and runner
- `finance/trading_engine.py` - Trade opportunity generator and ranker
- `finance/risk_analyzer.py` - Volatility and risk calculations
- `finance/uphold_api.py` - API integration with caching
- `finance/consumers.py` - WebSocket for frontend communication
- `finance/models.py` - Database schema (BotConfig, TradeHistory, etc.)

**Data Flow:**
```
Market Data → Cache → PortfolioOptimizer → RiskAnalyzer → Decision → Execution
     ↓
  WebSocket → Frontend
```

### Configuration

#### Via Django Admin
1. Go to http://localhost:8000/admin/
2. Configure in "Bot Config":
   - Risk tolerance (0.0-1.0)
   - Minimum confidence score
   - Trade size (fixed amount or percentage)
   - Check interval (seconds)
   - Cache TTL

#### Via Management Command
```bash
python manage.py runbot \
  --risk-level 0.6 \
  --min-confidence 0.75 \
  --interval 5 \
  --add-pair BTC-USD \
  --add-pair ETH-USD
```

#### Add Trading Pairs
```bash
python manage.py runbot --add-pair BTC-USD
python manage.py runbot --add-pair ETH-USD
```

### WebSocket Integration

Connect frontend to real-time updates:

```javascript
const ws = new WebSocket('ws://localhost:8000/ws/bot/status/');

// Get current status
ws.send(JSON.stringify({action: 'get_status'}));

// Listen for trade execution
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  if (data.type === 'trade_executed') {
    console.log('Trade executed:', data.data);
  }
};

// Update configuration
ws.send(JSON.stringify({
  action: 'update_config',
  data: {
    is_active: true,
    risk_tolerance: 0.6,
    min_confidence: 0.7
  }
}));
```

### Running with WebSockets (Daphne)

For real-time updates, run with Daphne ASGI server:

```bash
# Terminal 1: Start ASGI server with WebSocket support
daphne -b 0.0.0.0 -p 8000 core.asgi:application

# Terminal 2: Run the bot
python manage.py runbot
```

### Database Models

**BotConfig** - Global bot settings (active, risk tolerance, trade size, intervals)  
**TradingPair** - Trading pairs to monitor (enabled, priority)  
**TradeHistory** - Executed trades (max 100, auto-cleanup)  
**PriceSnapshot** - Cached price data  

### Risk Management

The bot calculates a **risk score** for each potential trade:

```
Risk Score = Volatility / (Confidence × Expected_Return)
```

Trades execute only if:
- Confidence >= `min_confidence_score` (default 0.7)
- Risk Score <= `risk_tolerance` (default 0.5)
- Expected return > 0.1%

### Trade History Cleanup

- Automatically keeps last 100 trades
- Older trades deleted to prevent DB bloat
- Manual cleanup available via Django shell

### Performance Tuning

- **Cache TTL**: 3-5 seconds (balance freshness vs API load)
- **Check Interval**: 3-5 seconds (frequency of trade checks)
- **Trade Size**: 10% of holdings (default percentage)

### Monitoring

#### View Recent Trades
```python
python manage.py shell
from finance.models import TradeHistory
trades = TradeHistory.objects.all()[:20]
for t in trades:
    print(f"{t.from_pair}→{t.to_pair}: {t.decision} ({t.status})")
```

#### Check Bot Status
Via admin: http://localhost:8000/admin/finance/botconfig/

#### View Logs
```bash
python manage.py runbot  # Shows real-time logs
```

### Documentation

See **BOT_DOCUMENTATION.md** for:
- Complete API reference
- WebSocket message formats
- Troubleshooting guide
- Advanced configuration
- Best practices

### Example Workflow

```bash
# 1. Setup database
python manage.py migrate

# 2. Add trading pairs
python manage.py runbot --add-pair BTC-USD --add-pair ETH-USD

# 3. Start bot with moderate risk
python manage.py runbot --risk-level 0.5 --min-confidence 0.7

# 4. Monitor in admin panel
python manage.py runserver
# Visit http://localhost:8000/admin/finance/tradehistory/

# 5. Adjust settings via admin if needed
```

### Project Structure

```
finance/
├── models.py              # Database schema
├── bot_service.py         # Bot engine (AdvancedTradeBot, BotRunner)
├── trading_engine.py      # Trade optimizer (PortfolioOptimizer)
├── risk_analyzer.py       # Risk calculations (RiskAnalyzer)
├── uphold_api.py          # API handler with caching
├── cache.py               # Price caching (MarketDataCache)
├── consumers.py           # WebSocket consumer
├── routing.py             # WebSocket routing
├── admin.py               # Django admin configuration
├── views.py               # REST API endpoints
└── management/commands/
    └── runbot.py          # Bot management command

core/
├── settings.py            # Django settings (Channels config)
├── asgi.py                # ASGI application with Channels
└── urls.py                # URL routing
```

### Technologies

- **Django 6.0.2** - Web framework
- **Channels 4.1.0** - WebSocket support
- **Daphne 4.1.2** - ASGI server
- **Uphold API** - Exchange integration
- **SQLite** - Database (development)

### Future Enhancements

- [ ] Machine learning price prediction
- [ ] Multi-exchange support
- [ ] Paper trading mode
- [ ] Advanced charting
- [ ] Mobile app
- [ ] Backtesting engine
- [ ] Stop-loss/take-profit limits

### License

BugsByte Project 2026

---

**Need Help?** See BOT_DOCUMENTATION.md or check finance/admin.py for configuration options.
