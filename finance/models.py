from django.db import models
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator


class TradingPair(models.Model):
    """User-configured trading pairs to monitor."""
    pair_symbol = models.CharField(max_length=20, unique=True)  # e.g., "BTC-USD"
    is_enabled = models.BooleanField(default=True)
    priority = models.IntegerField(default=0)  # Higher = more priority
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-priority', 'pair_symbol']

    def __str__(self):
        return f"{self.pair_symbol} ({'enabled' if self.is_enabled else 'disabled'})"


class BotConfig(models.Model):
    """Global bot configuration."""
    is_active = models.BooleanField(default=False)
    risk_tolerance = models.FloatField(
        default=0.5,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text="Risk tolerance (0.0=very conservative, 1.0=aggressive)"
    )
    min_confidence_score = models.FloatField(
        default=0.7,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text="Minimum confidence to execute trade"
    )
    trade_size_amount = models.DecimalField(
        max_digits=15, decimal_places=8, null=True, blank=True,
        help_text="Fixed amount per trade (if percentage not set)"
    )
    trade_size_percentage = models.FloatField(
        default=0.1,
        validators=[MinValueValidator(0.01), MaxValueValidator(1.0)],
        help_text="Percentage of holdings to trade (0.0-1.0)"
    )
    check_interval_seconds = models.IntegerField(
        default=5,
        validators=[MinValueValidator(1), MaxValueValidator(300)]
    )
    cache_ttl_seconds = models.IntegerField(
        default=3,
        validators=[MinValueValidator(1), MaxValueValidator(60)],
        help_text="Price cache time-to-live in seconds"
    )
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Bot Config"

    def __str__(self):
        return f"Bot Config (active={self.is_active}, risk={self.risk_tolerance})"

    @classmethod
    def get_config(cls):
        """Get or create default config."""
        config, _ = cls.objects.get_or_create(pk=1)
        return config


class TradeHistory(models.Model):
    """Record of executed trades (limited to last 100)."""
    DECISION_CHOICES = [
        ('BUY', 'Buy'),
        ('SELL', 'Sell'),
        ('HOLD', 'Hold'),
        ('NONE', 'No Action'),
    ]
    
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('EXECUTED', 'Executed'),
        ('FAILED', 'Failed'),
    ]

    from_pair = models.CharField(max_length=20)  # e.g., "BTC"
    to_pair = models.CharField(max_length=20)   # e.g., "USD"
    decision = models.CharField(max_length=10, choices=DECISION_CHOICES)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='PENDING')
    
    amount = models.DecimalField(max_digits=15, decimal_places=8)
    from_price = models.DecimalField(max_digits=15, decimal_places=8)
    to_price = models.DecimalField(max_digits=15, decimal_places=8)
    
    confidence_score = models.FloatField(validators=[MinValueValidator(0.0), MaxValueValidator(1.0)])
    risk_score = models.FloatField(validators=[MinValueValidator(0.0), MaxValueValidator(1.0)])
    volatility = models.FloatField(default=0.0)
    
    reason = models.TextField(blank=True)  # Why this trade was recommended
    result = models.TextField(blank=True)  # Result after execution
    
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    executed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['-created_at'])]

    def __str__(self):
        return f"{self.from_pair}→{self.to_pair} ({self.decision}) @ {self.created_at.strftime('%H:%M:%S')}"

    @classmethod
    def cleanup_old_trades(cls, keep_count=100):
        """Keep only the last N trades, delete older ones."""
        total = cls.objects.count()
        if total > keep_count:
            to_delete = cls.objects.order_by('-created_at')[keep_count:]
            cls.objects.filter(pk__in=to_delete).delete()
            return total - keep_count
        return 0


class PriceSnapshot(models.Model):
    """Cached price data with timestamp."""
    pair = models.CharField(max_length=20, db_index=True)
    bid = models.DecimalField(max_digits=15, decimal_places=8)
    ask = models.DecimalField(max_digits=15, decimal_places=8)
    last = models.DecimalField(max_digits=15, decimal_places=8, null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['pair', '-updated_at']),
        ]
        unique_together = ('pair',)

    def __str__(self):
        return f"{self.pair}: bid={self.bid}, ask={self.ask} @ {self.updated_at.strftime('%H:%M:%S')}"

    def is_stale(self, ttl_seconds=3):
        """Check if cache is older than TTL."""
        age = (timezone.now() - self.updated_at).total_seconds()
        return age > ttl_seconds
