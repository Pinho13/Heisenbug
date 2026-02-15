from django.db.models import Min, Max
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
from .models import PriceSnapshot

def get_best_market_prices(pair):
    """
    Varre os snapshots dos últimos 60 segundos.
    Retorna o melhor preço para o utilizador (Smart Order Routing).
    """
    # Definimos um limite de tempo para não usar preços "mortos"
    recent_limit = timezone.now() - timedelta(seconds=60)
    
    # Agregação: Min para comprar barato, Max para vender caro
    result = PriceSnapshot.objects.filter(
        pair=pair,
        timestamp__gte=recent_limit
    ).aggregate(
        best_buy=Min('ask'),  # O melhor Ask (venda do mercado)
        best_sell=Max('bid')  # O melhor Bid (compra do mercado)
    )
    
    return {
        'buy': result['best_buy'],
        'sell': result['best_sell']
    }
