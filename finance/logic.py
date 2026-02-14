from .uphold_api import UpholdAPIHandler
from .models import AssetPool, TradeHistory

def run_bot_cycle(user):
    api = UpholdAPIHandler(api_key=user.profile.uphold_key) 
    pool = AssetPool.objects.filter(user=user, is_active=True)
    
    for asset in pool:
        ticker = api.get_ticker(f"{asset.symbol}-USD")
        if ticker:
            current_price = float(ticker['last'])
            print(f"Verificando {asset.symbol}: Preço atual {current_price}")
            
       
