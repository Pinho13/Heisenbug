import os
import django
from decimal import Decimal

# 1. Configurar Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'teu_projeto.settings') # AJUSTA O NOME AQUI
django.setup()

from django.contrib.auth.models import User
from finance.models import UserBalance, AssetPool, TradingPair, BotConfig

def run():
    print("--- A iniciar população das tuas tabelas ---")

    # Ativar o Bot nas Configurações
    config = BotConfig.get_config()
    config.is_active = True
    config.min_confidence_score = 0.1  # Baixo para forçar o trade no teste
    config.save()

    # Criar Pares que o bot vai monitorizar
    for p in ['BTC-USD', 'ETH-USD']:
        TradingPair.objects.get_or_create(pair_symbol=p, is_enabled=True)

    # Criar Users e dar-lhes "munição" (Balances) e "permissão" (AssetPool)
    users = [
        ('user_um', '1000.00', 'USD', 'BTC'),
        ('user_dois', '0.5', 'BTC', 'USD')
    ]

    for username, saldo, moeda_saldo, moeda_alvo in users:
        user, _ = User.objects.get_or_create(username=username)
        if _: user.set_password('senha123'); user.save()

        # Preencher UserBalance
        UserBalance.objects.update_or_create(
            user=user, 
            currency=moeda_saldo, 
            defaults={'amount': Decimal(saldo)}
        )

        # Preencher AssetPool (O bot só toca no que estiver aqui)
        AssetPool.objects.get_or_create(user=user, symbol=moeda_saldo, is_active=True)
        AssetPool.objects.get_or_create(user=user, symbol=moeda_alvo, is_active=True)

    print("--- Setup Concluído! ---")

if __name__ == "__main__":
    run()
