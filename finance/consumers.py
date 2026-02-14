"""Django Channels WebSocket consumer for real-time bot updates."""
import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import sync_to_async
from .models import TradeHistory, BotConfig

logger = logging.getLogger(__name__)


class BotStatusConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for streaming bot status, trades, and price updates.
    
    Handles:
    - Real-time trade execution notifications
    - Price updates
    - Bot status changes
    - Configuration updates from frontend
    """

    async def connect(self):
        """Accept WebSocket connection."""
        await self.accept()
        await self.send_json({
            'type': 'connection',
            'message': 'Connected to bot status stream'
        })
        logger.info("Bot status consumer connected")

    async def disconnect(self, close_code):
        """Handle disconnection."""
        logger.info(f"Bot status consumer disconnected: {close_code}")

    async def receive(self, text_data):
        """
        Receive message from WebSocket.
        
        Expected messages:
        {
            "action": "get_status" | "update_config" | "get_recent_trades",
            "data": {...}
        }
        """
        try:
            data = json.loads(text_data)
            action = data.get('action')

            if action == 'get_status':
                await self.send_bot_status()
            elif action == 'update_config':
                await self.update_bot_config(data.get('data', {}))
            elif action == 'get_recent_trades':
                await self.send_recent_trades(limit=data.get('limit', 10))
            elif action == 'get_top_trades':
                await self.send_top_opportunities(limit=data.get('limit', 5))
            else:
                await self.send_json({
                    'type': 'error',
                    'message': f'Unknown action: {action}'
                })
        except json.JSONDecodeError:
            await self.send_json({
                'type': 'error',
                'message': 'Invalid JSON'
            })
        except Exception as e:
            logger.error(f"Error in receive: {e}")
            await self.send_json({
                'type': 'error',
                'message': str(e)
            })

    async def send_json(self, data):
        """Send JSON message to client."""
        await self.send(text_data=json.dumps(data))

    async def send_bot_status(self):
        """Send current bot status."""
        config = await sync_to_async(BotConfig.get_config)()
        recent_trades = await sync_to_async(self._get_recent_trades)(limit=5)

        await self.send_json({
            'type': 'bot_status',
            'data': {
                'is_active': config.is_active,
                'risk_tolerance': config.risk_tolerance,
                'min_confidence': config.min_confidence_score,
                'check_interval': config.check_interval_seconds,
                'cache_ttl': config.cache_ttl_seconds,
                'recent_trades': recent_trades
            }
        })

    async def send_recent_trades(self, limit=10):
        """Send recent trades to client."""
        trades = await sync_to_async(self._get_recent_trades)(limit=limit)
        await self.send_json({
            'type': 'recent_trades',
            'data': trades
        })

    async def send_top_opportunities(self, limit=5):
        """Send top trade opportunities."""
        # This would integrate with the trading engine
        # For now, send empty list as placeholder
        await self.send_json({
            'type': 'top_opportunities',
            'data': []
        })

    async def broadcast_trade_execution(self, trade_data):
        """
        Broadcast trade execution to all connected clients.
        Called from bot when a trade is executed.
        """
        await self.send_json({
            'type': 'trade_executed',
            'data': trade_data,
            'timestamp': trade_data.get('executed_at', '')
        })

    async def broadcast_price_update(self, pair, price_data):
        """
        Broadcast price update.
        Called periodically during trading.
        """
        await self.send_json({
            'type': 'price_update',
            'pair': pair,
            'data': price_data
        })

    async def update_bot_config(self, config_data):
        """
        Update bot configuration from frontend.
        
        Expected data:
        {
            'is_active': bool,
            'risk_tolerance': float (0-1),
            'min_confidence': float (0-1),
            'check_interval': int,
            'cache_ttl': int
        }
        """
        try:
            config = await sync_to_async(BotConfig.get_config)()

            if 'is_active' in config_data:
                config.is_active = config_data['is_active']
            if 'risk_tolerance' in config_data:
                config.risk_tolerance = float(config_data['risk_tolerance'])
            if 'min_confidence' in config_data:
                config.min_confidence_score = float(config_data['min_confidence'])
            if 'check_interval' in config_data:
                config.check_interval_seconds = int(config_data['check_interval'])
            if 'cache_ttl' in config_data:
                config.cache_ttl_seconds = int(config_data['cache_ttl'])

            await sync_to_async(config.save)()

            await self.send_json({
                'type': 'config_updated',
                'message': 'Configuration updated successfully',
                'data': {
                    'is_active': config.is_active,
                    'risk_tolerance': config.risk_tolerance,
                    'min_confidence': config.min_confidence_score,
                    'check_interval': config.check_interval_seconds,
                    'cache_ttl': config.cache_ttl_seconds,
                }
            })
        except Exception as e:
            logger.error(f"Error updating config: {e}")
            await self.send_json({
                'type': 'error',
                'message': f'Failed to update configuration: {str(e)}'
            })

    @staticmethod
    def _get_recent_trades(limit=10):
        """Fetch recent trades from DB."""
        trades = TradeHistory.objects.all()[:limit]
        return [
            {
                'id': t.id,
                'from_pair': t.from_pair,
                'to_pair': t.to_pair,
                'decision': t.decision,
                'status': t.status,
                'amount': str(t.amount),
                'from_price': str(t.from_price),
                'to_price': str(t.to_price),
                'confidence': t.confidence_score,
                'risk': t.risk_score,
                'volatility': t.volatility,
                'reason': t.reason,
                'created_at': t.created_at.isoformat(),
                'executed_at': t.executed_at.isoformat() if t.executed_at else None
            }
            for t in trades
        ]
