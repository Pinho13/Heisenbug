
from django.http import JsonResponse
from django.db.models import F, Sum, ExpressionWrapper, DecimalField
from finance.TradeHistory import TradeHistory

def total_difference(request):
    expression = ExpressionWrapper(
        F('price_at_execution') - F('amount'),
        output_field=DecimalField(max_digits=20, decimal_places=8)
    )

    result = TradeHistory.objects.aggregate(
        total=Sum(expression)
    )

    return JsonResponse({
        "total": result["total"]
    })
