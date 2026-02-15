from django.urls import path
from hermes import views

urlpatterns = [
    path('', views.splash, name='splash'),
    path('home/', views.home, name='home'),
]
