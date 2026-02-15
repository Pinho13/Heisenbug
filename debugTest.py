import os
import django
from decimal import Decimal

# 1. Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from principal.models import User
from finance.models import UserBalance, TradingPair, BotConfig, PriceSnapshot
from finance.bot_service import TradeBot

def run_test():
    print("\n" + "="*40)
    print("🚀 INICIANDO TESTE DE MOTOR DE TRADING")
    print("="*40)

    # 2. Criar utilizador de teste se não existir
    user, created = User.objects.get_or_create(username="trader_test")
    if created:
        print(f"✅ Utilizador '{user.username}' criado.")

    # 3. Limpar saldos antigos e criar 1000 USD para o teste
    UserBalance.objects.filter(user=user).delete()
    balance = UserBalance.objects.create(
        user=user,
        currency="USD",
        amount=Decimal('1000.00')
    )
    print(f"✅ Saldo inicial: {balance.amount} {balance.currency}")

    # 4. Configurar o par e garantir que está ativo
    pair_symbol = "BTC-USD"
    TradingPair.objects.update_or_create(
        pair_symbol=pair_symbol, 
        defaults={'is_enabled': True}
    )

    # 5. Configurar Bot para ser agressivo
    config = BotConfig.get_config()
    config.is_active = True
    config.min_confidence_score = 0.0  # Aceita qualquer lucro
    config.risk_tolerance = 1.0       # Ignora risco alto
    config.save()
    print("✅ Configurações do Bot atualizadas (Modo Agressivo).")

    # 6. Criar oportunidade na PriceSnapshot
    # Precisamos de alguns snapshots para o cálculo de volatilidade não dar erro
    print(f"📊 Gerando snapshots para {pair_symbol}...")
    PriceSnapshot.objects.filter(pair=pair_symbol).delete()
    for i in range(5):
        PriceSnapshot.objects.create(
            pair=pair_symbol,
            bid=Decimal('50000.00'),
            ask=Decimal('50000.00'),
            currency="USD"
        )
    
    # A "Oportunidade": Preço de compra (ask) cai para 10 USD
    PriceSnapshot.objects.create(
        pair=pair_symbol,
        bid=Decimal('50000.00'),
        ask=Decimal('10.00'),
        currency="USD"
    )

    # 7. EXECUTAR O BOT
    print("\n⚙️  Executando TradeBot.run_iteration()...")
    bot = TradeBot()
    executed_trades = bot.run_iteration()

    # 8. VERIFICAR RESULTADOS
    print("\n" + "="*40)
    print("📊 RESULTADOS FINAIS")
    print("="*40)
    
    final_balances = UserBalance.objects.filter(user=user)
    if not final_balances.exists():
        print("❌ Erro: O utilizador não tem saldos.")
    else:
        for b in final_balances:
            print(f"💰 Moeda: {b.currency} | Saldo: {b.amount}")
            if b.currency == "BTC" and b.amount > 0:
                print("\n🎉 SUCESSO! O motor de trading comprou BTC com o saldo de USD.")

if __name__ == "__main__":
    run_test()
