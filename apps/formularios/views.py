from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.http import Http404
from django.shortcuts import redirect, render
from django.views import View
from django.views.generic import TemplateView

from apps.citas.services import TokenInvalido, obtener_cita_por_token
from apps.core.limites import agotado, ip_cliente, registrar_intento
from apps.core.mixins import RolRequerido
from apps.cuentas.models import Rol
from apps.formularios.constructor import construir_formulario
from apps.formularios.models import Formulario
from apps.formularios.selectors import (
    listar_formularios,
    llenados_recientes,
    version_para,
    version_publicada,
)
from apps.formularios.services import guardar_respuestas


def _privada(respuesta):
    """
    El token va en la URL: que no se guarde en cachés, no se filtre ni se indexe.
    `same-origin` y no `no-referrer`: con `no-referrer` el navegador manda
    `Origin: null` al enviar el formulario y la protección CSRF lo rechaza.
    """
    respuesta['Cache-Control'] = 'no-store'
    respuesta['Referrer-Policy'] = 'same-origin'
    respuesta['X-Robots-Tag'] = 'noindex, nofollow'
    return respuesta


class FormularioPublicoView(View):
    """
    Página pública del link/QR. No muestra ningún dato del paciente (CONTEXTO.md §5).
    Límite propio por IP: peticiones en general y, más estricto, links inválidos.
    """

    def dispatch(self, request, token):
        ip = ip_cliente(request)
        clave_invalidos = f'formulario-invalido:{ip}'
        demasiadas = registrar_intento(
            f'formulario:{ip}',
            maximo=settings.FORMULARIO_PETICIONES_MAX,
            ventana=settings.FORMULARIO_PETICIONES_VENTANA,
        )
        if demasiadas or agotado(
            clave_invalidos,
            maximo=settings.FORMULARIO_LINKS_INVALIDOS_MAX,
            ventana=settings.FORMULARIO_LINKS_INVALIDOS_VENTANA,
        ):
            return _privada(render(request, 'formularios/demasiados_intentos.html', status=429))

        try:
            self.cita = obtener_cita_por_token(token)
        except TokenInvalido:
            registrar_intento(
                clave_invalidos,
                maximo=settings.FORMULARIO_LINKS_INVALIDOS_MAX,
                ventana=settings.FORMULARIO_LINKS_INVALIDOS_VENTANA,
            )
            return _privada(render(request, 'formularios/link_invalido.html', status=404))

        self.version = version_para(self.cita.paciente)
        if self.version is None:
            return _privada(render(request, 'formularios/sin_formulario.html', status=503))
        self.Formulario = construir_formulario(self.version.esquema)
        return _privada(super().dispatch(request, token))

    def get(self, request, token):
        return self._mostrar(self.Formulario())

    def post(self, request, token):
        form = self.Formulario(request.POST)
        if form.is_valid():
            try:
                guardar_respuestas(self.cita, self.version, form.respuestas())
            except ValidationError:
                return render(request, 'formularios/link_invalido.html', status=404)
            return redirect('formulario_enviado')
        return self._mostrar(form)

    def _mostrar(self, form):
        return render(self.request, 'formularios/publico.html', {'form': form})


def formulario_enviado(request):
    return _privada(render(request, 'formularios/enviado.html'))


# Recepción


class FormularioListaView(RolRequerido, TemplateView):
    roles = [Rol.RECEPCIONISTA]
    template_name = 'formularios/lista.html'

    def get_context_data(self, **kwargs):
        formularios = list(listar_formularios())
        for formulario in formularios:
            formulario.publicada = version_publicada(formulario)
        return super().get_context_data(
            formularios=formularios, llenados=llenados_recientes(), **kwargs
        )


class FormularioDetalleView(RolRequerido, TemplateView):
    """Vista previa de la versión publicada, tal como la ve el paciente (deshabilitada)."""

    roles = [Rol.RECEPCIONISTA]
    template_name = 'formularios/detalle.html'

    def get_context_data(self, **kwargs):
        try:
            formulario = Formulario.objects.prefetch_related('versiones').get(pk=self.kwargs['pk'])
        except ObjectDoesNotExist as error:
            raise Http404 from error
        version = version_publicada(formulario)
        vista_previa = None
        if version:
            vista_previa = construir_formulario(version.esquema)()
            for campo in vista_previa.fields.values():
                campo.disabled = True
        return super().get_context_data(
            formulario=formulario, version=version, vista_previa=vista_previa, **kwargs
        )
