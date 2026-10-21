from django.contrib import admin
from django.urls import include, path

from apps.cuentas.views import InicioView

urlpatterns = [
    path('', InicioView.as_view(), name='inicio'),
    path('', include('apps.cuentas.urls')),
    path('pacientes/', include('apps.pacientes.urls')),
    path('personas/', include('apps.personas.urls')),
    path('admin/', admin.site.urls),
]
