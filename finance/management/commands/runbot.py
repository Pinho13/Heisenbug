from django.core.management.base import BaseCommand
from finance.bot_service import BotRunner
from finance.models import BotConfig, TradingPair


class Command(BaseCommand):
    help = "Run advanced trading bot with real-time decision engine"

    def add_arguments(self, parser):
        parser.add_argument(
            '--risk-level',
            type=float,
            default=None,
            help='Risk tolerance (0.0-1.0, 0=conservative, 1=aggressive)'
        )
        parser.add_argument(
            '--min-confidence',
            type=float,
            default=None,
            help='Minimum confidence score (0.0-1.0)'
        )
        parser.add_argument(
            '--interval',
            type=int,
            default=None,
            help='Check interval in seconds'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Run without executing trades (for testing)'
        )
        parser.add_argument(
            '--add-pair',
            type=str,
            default=None,
            help='Add a trading pair (e.g., BTC-USD)'
        )

    def handle(self, *args, **options):
        # Configure bot settings if provided
        config = BotConfig.get_config()

        if options['risk_level'] is not None:
            config.risk_tolerance = options['risk_level']
            self.stdout.write(f"Risk level: {options['risk_level']}")

        if options['min_confidence'] is not None:
            config.min_confidence_score = options['min_confidence']
            self.stdout.write(f"Min confidence: {options['min_confidence']}")

        if options['interval'] is not None:
            config.check_interval_seconds = options['interval']
            self.stdout.write(f"Check interval: {options['interval']}s")

        if options['dry_run']:
            self.stdout.write(self.style.WARNING("DRY RUN MODE - No trades will be executed"))

        config.is_active = True
        config.save()

        # Add trading pair if specified
        if options['add_pair']:
            pair = options['add_pair'].upper()
            tp, created = TradingPair.objects.get_or_create(pair_symbol=pair)
            if created:
                self.stdout.write(self.style.SUCCESS(f"Added trading pair: {pair}"))
            else:
                self.stdout.write(f"Trading pair already exists: {pair}")

        # Start bot
        self.stdout.write(self.style.SUCCESS("Starting trading bot..."))
        self.stdout.write(f"  Risk tolerance: {config.risk_tolerance}")
        self.stdout.write(f"  Min confidence: {config.min_confidence_score}")
        self.stdout.write(f"  Check interval: {config.check_interval_seconds}s")

        enabled_pairs = TradingPair.objects.filter(is_enabled=True).count()
        self.stdout.write(f"  Monitoring {enabled_pairs} trading pairs")

        runner = BotRunner()
        runner.start()

        try:
            import time
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("\nStopping bot..."))
            runner.stop()
            self.stdout.write(self.style.SUCCESS("Bot stopped"))

