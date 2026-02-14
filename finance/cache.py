from django.utils import timezone
from django.core.cache import cache
import json


class MarketDataCache:
    """
    Cache for market data with time to live.
    Using Django's cache framework
    """
    CACHE_PREFIX = "market_data:"
    TICKER_CACHE_PREFIX = "ticker:"

    @classmethod
    def get_price(cls, pair: str, ttl_seconds: int = 3):

        key = f"{cls.CACHE_PREFIX}{pair}"
        data = cache.get(key)

        if data:
            age = (timezone.now() - data.get('cached_at')).total_seconds()
            if age <= ttl_seconds:
                return data
        return None

    @classmethod
    def set_price(cls, pair: str, ticker_data: dict, ttl_seconds: int = 3):
        """
        Cache a price update
        """
        key = f"{cls.CACHE_PREFIX}{pair}"
        cache_data = {
            'pair': pair,
            'bid': ticker_data.get('bid'),
            'ask': ticker_data.get('ask'),
            'last': ticker_data.get('last'),
            'cached_at': timezone.now(),
        }

        cache.set(key, cache_data, timeout=ttl_seconds+5)

    @classmethod
    def get_all_prices(cls, pairs: list, ttl_seconds: int = 3) -> dict:
        """Returns a Dict(pair: price_data) for valid cached items"""
        result = {}
        for pair in pairs:
            data = cls.get_price(pair, ttl_seconds)
            if data:
                result[pair] = data
        return result

    @classmethod
    def clear_pair(cls, pair: str):
        """clear cache for a specific pair"""
        key = f"{cls.CACHE_PREFIX}{pair}"
        cache.delete(key)

    @classmethod
    def clear_all(cls):
        """Clear all market data cache"""
        # WARNING : simple implementation, might need to track keys in prod
        cache.clear()

    @classmethod
    def needs_refresh(cls, pair: str, ttl_seconds: int = 3) -> bool:
        """Returns boolean on whether the cached pair needs refresh"""
        data = cache.get(f"{cls.CACHE_PREFIX}{pair}")
        if not data:
            return True
        age = (timezone.now() - data.get('cached_at')).total_seconds()
        return age > ttl_seconds
