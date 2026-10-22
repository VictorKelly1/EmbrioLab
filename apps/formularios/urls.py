from django.urls import path

from apps.formularios import views

app_name = 'formularios'

urlpatterns = [
    path('', views.FormularioListaView.as_view(), name='lista'),
    path('<int:pk>/', views.FormularioDetalleView.as_view(), name='detalle'),
]
