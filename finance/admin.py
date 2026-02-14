from django.contrib import admin
from .models import TradingPair, BotConfig, TradeHistory, PriceSnapshot


@admin.register(BotConfig)
class BotConfigAdmin(admin.ModelAdmin):
    list_display = ('is_active', 'risk_tolerance', 'min_confidence_score', 'check_interval_seconds')
    fieldsets = (
        ('Status', {
            'fields': ('is_active',)
        }),
        ('Risk Management', {
            'fields': ('risk_tolerance', 'min_confidence_score')
        }),
        ('Trade Configuration', {
            'fields': ('trade_size_amount', 'trade_size_percentage')
        }),
        ('Timing', {
            'fields': ('check_interval_seconds', 'cache_ttl_seconds')
        }),
    )


@admin.register(TradingPair)
class TradingPairAdmin(admin.ModelAdmin):
    list_display = ('pair_symbol', 'is_enabled', 'priority', 'created_at')
    list_filter = ('is_enabled', 'created_at')
    search_fields = ('pair_symbol',)
    ordering = ('-priority', 'pair_symbol')
    fieldsets = (
        ('Pair Info', {
            'fields': ('pair_symbol',)
        }),
        ('Configuration', {
            'fields': ('is_enabled', 'priority')
        }),
    )


@admin.register(TradeHistory)
class TradeHistoryAdmin(admin.ModelAdmin):
    list_display = ('from_pair', 'to_pair', 'decision', 'status', 'confidence_score', 'risk_score', 'created_at')
    list_filter = ('status', 'decision', 'created_at')
    search_fields = ('from_pair', 'to_pair')
    readonly_fields = ('created_at', 'executed_at', 'result')
    ordering = ('-created_at',)

    fieldsets = (
        ('Trade Details', {
            'fields': ('from_pair', 'to_pair', 'amount', 'decision', 'status')
        }),
        ('Pricing', {
            'fields': ('from_price', 'to_price')
        }),
        ('Analysis', {
            'fields': ('confidence_score', 'risk_score', 'volatility', 'reason')
        }),
        ('Execution', {
            'fields': ('created_at', 'executed_at', 'result')
        }),
    )


@admin.register(PriceSnapshot)
class PriceSnapshotAdmin(admin.ModelAdmin):
    list_display = ('pair', 'bid', 'ask', 'last', 'updated_at')
    list_filter = ('pair', 'updated_at')
    search_fields = ('pair',)
    readonly_fields = ('pair', 'created_at', 'updated_at')
    ordering = ('-updated_at',)
