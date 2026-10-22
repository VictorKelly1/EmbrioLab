from django.urls import path

from apps.estudios import views

app_name = 'estudios'

urlpatterns = [
    path('', views.EstudioListaView.as_view(), name='lista'),
    path('<int:pk>/', views.EstudioDetalleView.as_view(), name='detalle'),
    path('<int:pk>/alias/nuevo/', views.AliasCrearView.as_view(), name='alias_crear'),
    path('alias/<int:pk>/editar/', views.AliasEditarView.as_view(), name='alias_editar'),
    path('alias/<int:pk>/eliminar/', views.AliasEliminarView.as_view(), name='alias_eliminar'),
    path(
        '<int:pk>/referencias/nueva/',
        views.ReferenciaCrearView.as_view(),
        name='referencia_crear',
    ),
    path(
        'referencias/<int:pk>/editar/',
        views.ReferenciaEditarView.as_view(),
        name='referencia_editar',
    ),
    path(
        'referencias/<int:pk>/activo/',
        views.ReferenciaActivoView.as_view(),
        name='referencia_activo',
    ),
]
