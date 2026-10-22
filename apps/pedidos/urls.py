from django.urls import path

from apps.pedidos import views

app_name = 'pedidos'

urlpatterns = [
    path('', views.PedidoListaView.as_view(), name='lista'),
    path('nuevo/', views.PedidoCrearView.as_view(), name='crear'),
    path('sugerencias/', views.SugerenciasView.as_view(), name='sugerencias'),
    path('<int:pk>/', views.PedidoDetalleView.as_view(), name='detalle'),
    path('<int:pk>/doctor/', views.PedidoDoctorView.as_view(), name='doctor'),
    path('<int:pk>/pago/', views.PedidoPagoView.as_view(), name='pago'),
    path('<int:pk>/estudios/', views.PedidoAgregarEstudioView.as_view(), name='agregar_estudio'),
    path(
        'estudios/<int:pk>/',
        views.EstudioPedidoActualizarView.as_view(),
        name='estudio_actualizar',
    ),
    path(
        'estudios/<int:pk>/quitar/', views.EstudioPedidoQuitarView.as_view(), name='estudio_quitar'
    ),
]
