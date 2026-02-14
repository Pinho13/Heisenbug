from django.contrib import admin
from django.urls import path
from hermes import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.home, name='home'),
]