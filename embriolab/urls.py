from django.contrib import admin
from django.urls import include, path

from apps.cuentas.views import InicioView
from apps.formularios.views import FormularioPublicoView, formulario_enviado

urlpatterns = [
    path('', InicioView.as_view(), name='inicio'),
    path('', include('apps.cuentas.urls')),
    path('citas/', include('apps.citas.urls')),
    path('formularios/', include('apps.formularios.urls')),
    # Públicas, sin sesión: el link/QR que recibe el paciente.
    path('f/enviado/', formulario_enviado, name='formulario_enviado'),
    path('f/<str:token>/', FormularioPublicoView.as_view(), name='formulario_publico'),
    path('pacientes/', include('apps.pacientes.urls')),
    path('personas/', include('apps.personas.urls')),
    path('admin/', admin.site.urls),
]
