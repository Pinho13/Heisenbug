from django.db.models import Min, Max
from finance.models import PriceSnapshot


def get_best_bid(pair):
    """Returns the lowest bid for a given pair (best price to buy at)."""
    result = PriceSnapshot.objects.filter(
        pair=pair
    ).aggregate(best_bid=Min('bid'))
    return result['best_bid']


def get_best_ask(pair):
    """Returns the highest ask for a given pair (best price to sell at)."""
    result = PriceSnapshot.objects.filter(
        pair=pair
    ).aggregate(best_ask=Max('ask'))
    return result['best_ask']


def get_best_prices(pair):
    """Returns both the best bid (lowest) and best ask (highest) for a pair."""
    result = PriceSnapshot.objects.filter(
        pair=pair
    ).aggregate(
        best_bid=Min('bid'),
        best_ask=Max('ask'),
    )
    return {
        'pair': pair,
        'best_bid': result['best_bid'],
        'best_ask': result['best_ask'],
    }


def get_best_prices_all_pairs():
    """Returns the best bid and best ask for every pair in the database."""
    pairs = PriceSnapshot.objects.values_list(
        'pair', flat=True
    ).distinct()
    return {pair: get_best_prices(pair) for pair in pairs}
