import time
from .bot_logic import SimpleBot
import os

# Time sleeping in the loop
TIME_BETWEEN_CHECKS = 60

def run_bot_loop():
    api_key = os.environ.get("UPHOLD_API_KEY")
    bot = SimpleBot(api_key)

    # Configuration
    pair = "BTC-USD"
    buy_threshold = 25000
    sell_threshold = 27000

    while True:
        bot.check_price_and_trade(pair, buy_threshold, sell_threshold)
        time.sleep(TIME_BETWEEN_CHECKS)
