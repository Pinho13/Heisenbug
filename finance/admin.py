from django.contrib import admin
from .models import AssetPool, TradeHistory, UserBalance, PortfolioSnapshot, TradingPair, BotConfig


@admin.register(AssetPool)
class AssetPoolAdmin(admin.ModelAdmin):
    list_display = ('symbol', 'user', 'is_active', 'target_allocation')
    list_filter = ('is_active', 'user')


@admin.register(TradeHistory)
class TradeHistoryAdmin(admin.ModelAdmin):
    list_display = ('pair', 'operation', 'amount',
                    'price_at_execution', 'timestamp')
    readonly_fields = ('timestamp',)

@admin.register(UserBalance)
class UserBalanceAdmin(admin.ModelAdmin):
    list_display = ('user', 'currency', 'amount', 'updated_at')
    list_filter = ('currency', 'user')

@admin.register(PortfolioSnapshot)
class PortfolioSnapshotAdmin(admin.ModelAdmin):
    list_display = ('user', 'currency', 'amount', 'timestamp')

@admin.register(TradingPair)
class TradingPairAdmin(admin.ModelAdmin):
    list_display = ('pair_symbol', 'is_enabled')

@admin.register(BotConfig)
class BotConfigAdmin(admin.ModelAdmin):
    list_display = ('id', 'is_active', 'check_interval_seconds')
