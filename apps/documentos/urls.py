from django.urls import path

from apps.documentos import views

app_name = 'documentos'

urlpatterns = [
    path(
        'pedidos/<int:pk>/resultados.pdf',
        views.ResultadosPDFView.as_view(),
        name='resultados',
    ),
]
