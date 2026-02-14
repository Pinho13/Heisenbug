from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ('username', 'email', 'verified',
                    'kyc_status', 'created_at')
    list_filter = ('verified', 'kyc_status', 'created_at')
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Custom Fields', {'fields': ('verified',
         'crypto_wallet_address', 'kyc_status')}),
    )
