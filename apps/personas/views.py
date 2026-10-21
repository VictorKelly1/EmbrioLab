from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.views import View

from apps.core.mixins import RolRequerido
from apps.cuentas.models import Rol
from apps.personas.models import Persona


class FotoPersonaView(RolRequerido, View):
    """Entrega la foto privada solo al personal con sesión; nunca la cachea el navegador."""

    roles = tuple(Rol)

    def get(self, request, pk):
        persona = get_object_or_404(Persona, pk=pk)
        if not persona.foto:
            raise Http404
        respuesta = FileResponse(persona.foto.open('rb'))
        respuesta['Cache-Control'] = 'private, no-store'
        respuesta['X-Content-Type-Options'] = 'nosniff'
        return respuesta
