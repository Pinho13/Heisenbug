from django.core.management.base import BaseCommand
from finance.tasks import run_bot_loop


class Command(BaseCommand):
    help = "Run Hermes!"

    def handle(self, *args, **kwargs):
        run_bot_loop()
