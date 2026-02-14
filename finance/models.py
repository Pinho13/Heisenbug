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

from django.db import models
from django.contrib.auth.models import User
from decimal import Decimal

class BotConfig(models.Model):
    # status
    is_active = models.BooleanField(default=False, verbose_name="Bot Ativo")
    check_interval_seconds = models.IntegerField(default=60, help_text="Intervalo entre análises")
    cache_ttl_seconds = models.IntegerField(default=10, help_text="Tempo de vida do cache de preços")

    # riscos
    risk_tolerance = models.FloatField(default=0.5, help_text="0.0 (Conservador) a 1.0 (Arriscado)")
    min_confidence_score = models.FloatField(default=0.6, help_text="Score mínimo para executar trade")
    
    # tamanhos
    trade_size_percentage = models.FloatField(default=0.1, help_text="Percentagem da banca por trade (ex: 0.1 = 10%)")
    trade_size_amount = models.DecimalField(
        max_digits=20, decimal_places=8, null=True, blank=True, 
        help_text="Valor fixo opcional (se definido, ignora a percentagem)"
    )

    class Meta:
        verbose_name = "Configuração do Bot"

    @classmethod
    def get_config(cls):
        config, created = cls.objects.get_or_create(id=1)
        return config

    def __str__(self):
        return f"Configuração Global (Ativo: {self.is_active})"