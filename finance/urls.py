from django.urls import path
from . import views

urlpatterns = [
    path('ticker/btc/', views.btc_usd_price, name='btc_price'),
    path('ticker/<str:pair>/', views.price_view, name='price_view'),
]
