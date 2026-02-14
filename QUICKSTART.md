"""
QUICK START GUIDE - Trading Bot
================================

1. INSTALL & SETUP
   pip install -r requirements.txt
   python manage.py migrate
   python manage.py createsuperuser

2. ADD TRADING PAIRS
   python manage.py runbot --add-pair BTC-USD
   python manage.py runbot --add-pair ETH-USD

3. START THE BOT
   # Option A: Simple start (with WebSocket via Daphne)
   daphne -b 0.0.0.0 -p 8000 core.asgi:application
   # Then in another terminal:
   python manage.py runbot

   # Option B: With custom settings
   python manage.py runbot --risk-level 0.5 --min-confidence 0.7 --interval 3

4. MONITOR VIA ADMIN
   python manage.py runserver
   # Visit: http://localhost:8000/admin/
   # Login with superuser credentials

5. CONFIGURE BOT
   Admin Panel → Bot Config:
   - Set risk_tolerance (0.0-1.0, default 0.5)
   - Set min_confidence_score (0.0-1.0, default 0.7)
   - Set trade_size_percentage (0.01-1.0, default 0.1)
   - Set check_interval_seconds (1-300, default 5)

6. MONITOR TRADES
   Admin Panel → Trade History:
   - View all executed trades
   - Check confidence and risk scores
   - See trade reasoning and results

7. WEBSOCKET CONNECTION (for frontend)
   ws://localhost:8000/ws/bot/status/

   Example message:
   {"action": "get_status"}
   
   Example response:
   {
     "type": "bot_status",
     "data": {
       "is_active": true,
       "risk_tolerance": 0.5,
       "recent_trades": [...]
     }
   }

---

CONFIGURATION QUICK REFERENCE
==============================

Risk Profiles:
  Conservative: --risk-level 0.3 (very few trades, safer)
  Moderate:     --risk-level 0.5 (balanced)
  Aggressive:   --risk-level 0.8 (more trades, higher risk)

Trade Frequency:
  High:   --interval 1-2 (every 1-2 seconds)
  Medium: --interval 3-5 (every 3-5 seconds)
  Low:    --interval 10-30 (every 10-30 seconds)

Multiple Pairs:
  python manage.py runbot \\
    --add-pair BTC-USD \\
    --add-pair ETH-USD \\
    --add-pair LTC-USD

Dry-Run Mode (testing):
  python manage.py runbot --dry-run

---

TROUBLESHOOTING
===============

Bot Not Starting?
  1. Check migrations: python manage.py migrate
  2. Check logs: python manage.py runbot
  3. Verify Uphold API connectivity

No Trades Being Made?
  1. Verify pairs are enabled in Admin → Trading Pairs
  2. Check min_confidence_score not too high
  3. Ensure portfolio has balances
  4. Check bot is active: BotConfig.is_active = True

WebSocket Not Connecting?
  1. Use Daphne: daphne core.asgi:application (not runserver)
  2. Try: ws://localhost:8000/ws/bot/status/
  3. Check browser console for errors

High API Usage?
  1. Increase cache_ttl_seconds (default 3)
  2. Increase check_interval_seconds (default 5)
  3. Reduce number of trading pairs

---

FILES CREATED
=============

NEW:
  finance/bot_service.py      → Main bot engine (AdvancedTradeBot, BotRunner)
  finance/trading_engine.py   → Trade optimizer (PortfolioOptimizer)
  finance/risk_analyzer.py    → Risk calculations (RiskAnalyzer)
  finance/cache.py            → Price caching (MarketDataCache)
  finance/consumers.py        → WebSocket consumer
  finance/routing.py          → WebSocket routing
  BOT_DOCUMENTATION.md        → Full documentation
  
MODIFIED:
  finance/models.py           → Added 4 new models (BotConfig, TradingPair, etc)
  finance/uphold_api.py       → Added caching, batch fetching, portfolio snapshot
  finance/admin.py            → Admin configuration for all models
  finance/management/commands/runbot.py → Enhanced with options
  core/settings.py            → Channels config
  core/asgi.py                → Channels routing
  requirements.txt            → Added channels, daphne
  README.md                   → Full project documentation

---

NEXT STEPS
==========

1. Test with small risk tolerance first
2. Monitor a few trades manually
3. Adjust settings in admin panel
4. Increase risk level gradually
5. Monitor database size (trade history cleanup automatic)
6. Connect frontend via WebSocket

For full documentation: see BOT_DOCUMENTATION.md
For API reference: see finance/consumers.py (WebSocket consumer)
For configuration: see finance/models.py (BotConfig model)

"""
print(__doc__)
