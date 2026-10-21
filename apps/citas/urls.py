from django.urls import path

from apps.citas import views

app_name = 'citas'

urlpatterns = [
    path('', views.CalendarioView.as_view(), name='calendario'),
    path('agendar/', views.AgendarView.as_view(), name='agendar'),
    path('sin-cita/', views.EspontaneaView.as_view(), name='espontanea'),
    path('buscar-paciente/', views.BuscarPacienteView.as_view(), name='buscar_paciente'),
    path('<int:pk>/', views.CitaDetalleView.as_view(), name='detalle'),
    path('<int:pk>/reprogramar/', views.ReprogramarView.as_view(), name='reprogramar'),
    path('<int:pk>/estado/', views.CitaAccionView.as_view(), name='accion'),
    path('<int:pk>/link-formulario/', views.GenerarQRView.as_view(), name='generar_qr'),
]
