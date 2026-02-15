from django.urls import path
from . import views

app_name = 'hermes'

urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('api/chart-data/', views.get_chart_data, name='chart_data'),
    path('api/bot/start/', views.bot_start, name='bot_start'),
    path('api/bot/stop/', views.bot_stop, name='bot_stop'),
    path('api/bot/status/', views.bot_status, name='bot_status'),
]
