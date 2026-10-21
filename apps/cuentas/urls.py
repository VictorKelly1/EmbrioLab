from django.urls import path

from apps.cuentas import views

app_name = 'cuentas'

urlpatterns = [
    path('entrar/', views.EntrarView.as_view(), name='entrar'),
    path('salir/', views.SalirView.as_view(), name='salir'),
]
