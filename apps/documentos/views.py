from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.views import View

from apps.core.mixins import RolRequerido
from apps.cuentas.models import Rol
from apps.documentos.pdf import nombre_archivo, pdf_resultados
from apps.pedidos.models import Pedido
from apps.pedidos.selectors import estudios_completados


class ResultadosPDFView(RolRequerido, View):
    """
    PDF de los estudios completados del pedido, generado en cada petición. Con
    `?estudio=<id>` (se puede repetir), solo esos.
    """

    roles = [Rol.RECEPCIONISTA, Rol.QUIMICO]

    def get(self, request, pk):
        pedido = get_object_or_404(Pedido, pk=pk)
        ids = [i for i in request.GET.getlist('estudio') if i.isdigit()]
        estudios = list(estudios_completados(pedido, ids or None))
        if not estudios:
            raise Http404('El pedido no tiene estudios completados.')
        respuesta = HttpResponse(pdf_resultados(estudios), content_type='application/pdf')
        respuesta['Content-Disposition'] = f'inline; filename="{nombre_archivo(estudios)}"'
        # Datos de salud: que ni el navegador ni un proxy lo guarden.
        respuesta['Cache-Control'] = 'no-store'
        return respuesta
