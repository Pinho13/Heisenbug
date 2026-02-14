from django.contrib import admin
from .models import AssetPool, TradeHistory

@admin.register(AssetPool)
class AssetPoolAdmin(admin.ModelAdmin):
    list_display = ('symbol', 'user', 'is_active', 'target_allocation')
    list_filter = ('is_active', 'user')

@admin.register(TradeHistory)
class TradeHistoryAdmin(admin.ModelAdmin):
    list_display = ('pair', 'operation', 'amount', 'price_at_execution', 'timestamp')
    readonly_fields = ('timestamp',) # Impede que alteres a hora manualmente