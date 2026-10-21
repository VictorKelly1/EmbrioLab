from django.urls import path

from apps.pacientes import views

app_name = 'pacientes'

urlpatterns = [
    path('', views.PacienteListaView.as_view(), name='lista'),
    path('nuevo/', views.PacienteCrearView.as_view(), name='crear'),
    path('<int:pk>/', views.PacienteDetalleView.as_view(), name='detalle'),
    path('<int:pk>/editar/', views.PacienteEditarView.as_view(), name='editar'),
    path('<int:pk>/baja/', views.PacienteBajaView.as_view(), name='baja'),
    path('doctores/', views.DoctorListaView.as_view(), name='doctores'),
    path('doctores/nuevo/', views.DoctorCrearView.as_view(), name='doctor_crear'),
    path('doctores/<int:pk>/editar/', views.DoctorEditarView.as_view(), name='doctor_editar'),
]
