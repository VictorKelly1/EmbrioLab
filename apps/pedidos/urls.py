from django.urls import path

from apps.pedidos import views

app_name = 'pedidos'

urlpatterns = [
    path('', views.PedidoListaView.as_view(), name='lista'),
    path('nuevo/', views.PedidoCrearView.as_view(), name='crear'),
    path('cola/', views.ColaView.as_view(), name='cola'),
    path('sugerencias/', views.SugerenciasView.as_view(), name='sugerencias'),
    path('<int:pk>/', views.PedidoDetalleView.as_view(), name='detalle'),
    path('<int:pk>/doctor/', views.PedidoDoctorView.as_view(), name='doctor'),
    path('<int:pk>/observaciones/', views.PedidoObservacionView.as_view(), name='observacion'),
    path('<int:pk>/pago/', views.PedidoPagoView.as_view(), name='pago'),
    path('<int:pk>/estudios/', views.PedidoAgregarEstudioView.as_view(), name='agregar_estudio'),
    path('<int:pk>/enviar/', views.PedidoEnviarResultadosView.as_view(), name='enviar'),
    path(
        'estudios/<int:pk>/',
        views.EstudioPedidoActualizarView.as_view(),
        name='estudio_actualizar',
    ),
    path(
        'estudios/<int:pk>/resultados/',
        views.EstudioPedidoResultadosView.as_view(),
        name='resultados',
    ),
    path('pacientes/<int:pk>/tomar/', views.PacienteTomarView.as_view(), name='paciente_tomar'),
    path('pacientes/<int:pk>/soltar/', views.PacienteSoltarView.as_view(), name='paciente_soltar'),
    path('pacientes/<int:pk>/pasar/', views.PacientePasarView.as_view(), name='paciente_pasar'),
    path(
        'estudios/<int:pk>/quitar/', views.EstudioPedidoQuitarView.as_view(), name='estudio_quitar'
    ),
]
