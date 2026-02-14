from django.db import models
from django.conf import settings


class AssetPool(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL,
                             on_delete=models.CASCADE)
    symbol = models.CharField(max_length=20)
    is_active = models.BooleanField(default=True)
    target_allocation = models.FloatField(default=0.0)

    def __str__(self):
        return f"{self.symbol} - {self.user.username}"


class TradeHistory(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True)
    pair = models.CharField(max_length=20) 
    operation = models.CharField(max_length=10) 
    amount = models.DecimalField(max_digits=20, decimal_places=8)
    price_at_execution = models.DecimalField(max_digits=20, decimal_places=8)
    status = models.CharField(max_length=20, default="EXECUTED")
    confidence_score = models.FloatField(null=True)
    reason = models.TextField(null=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    @classmethod
    def cleanup_old_trades(cls, keep_count=500):
        ids_to_keep = cls.objects.order_by('-timestamp').values_list('id', flat=True)[:keep_count]
        cls.objects.exclude(id__in=ids_to_keep).delete()

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

class TradingPair(models.Model):
    pair_symbol = models.CharField(max_length=20, unique=True, help_text="Ex: BTC-USD")
    is_enabled = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.pair_symbol} (Ativo: {self.is_enabled})"

class PriceSnapshot(models.Model):
    pair = models.CharField(max_length=20, db_index=True)
    bid = models.DecimalField(max_digits=20, decimal_places=8)
    ask = models.DecimalField(max_digits=20, decimal_places=8)
    last = models.DecimalField(max_digits=20, decimal_places=8)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        get_latest_by = 'timestamp'

    def __str__(self):
        return f"{self.pair} @ {self.last} em {self.timestamp}"