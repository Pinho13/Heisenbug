from django.db import models
from django.contrib.auth.models import User

class AssetPool(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    symbol = models.CharField(max_length=20)
    is_active = models.BooleanField(default=True)
    target_location = models.FloatField(default=0.0)

    def __str__(self):
        return f"{self.symbol} - {self.user.username}"

class TradeHistory(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    pair = models.CharField(max_length=20) 
    operation = models.CharField(max_length=10) 
    amount = models.DecimalField(max_digits=20, decimal_places=8)
    price_at_execution = models.DecimalField(max_digits=20, decimal_places=8)
    timestamp = models.DateTimeField(auto_now_add=True)
    profit_loss = models.FloatField(null=True, blank=True) 

    def __str__(self):
        return f"{self.operation} {self.pair} - {self.timestamp}"

