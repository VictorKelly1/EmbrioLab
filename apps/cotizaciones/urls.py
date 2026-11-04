from django.urls import path

from apps.cotizaciones import views

app_name = 'cotizaciones'

urlpatterns = [
    path('', views.CotizacionView.as_view(), name='cotizar'),
]
