from django.urls import path
from hermes import views

urlpatterns = [
    path('', views.home, name='home'),
]
