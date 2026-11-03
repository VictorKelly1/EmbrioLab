from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.views.generic import TemplateView

from apps.core.forms import aplicar_errores
from apps.core.mixins import RolRequerido
from apps.cotizaciones.cotizacion import cotizar
from apps.cotizaciones.envio import destinos_para, enviar_cotizacion
from apps.cotizaciones.forms import CotizacionForm
from apps.cuentas.models import Rol
from apps.documentos.pdf import nombre_cotizacion, pdf_cotizacion
from apps.notificaciones.models import Canal


class CotizacionView(RolRequerido, TemplateView):
    """
    Arma un paquete temporal de estudios con su total, y lo descarga en PDF o lo envía
    al paciente (o a un correo/WhatsApp escrito a mano). Decidido: solo la recepción.
    """

    roles = [Rol.RECEPCIONISTA]
    template_name = 'cotizaciones/cotizar.html'

    def get(self, request, *args, **kwargs):
        return self.render_to_response(self.get_context_data(form=CotizacionForm()))

    def post(self, request, *args, **kwargs):
        form = CotizacionForm(request.POST)
        if form.is_valid():
            try:
                cotizacion = cotizar(form.estudios_en_orden(), cliente=form.nombre_cliente())
                if request.POST.get('accion') == 'enviar':
                    self._enviar(form, cotizacion)
                else:
                    return self._pdf(cotizacion)
            except ValidationError as error:
                aplicar_errores(form, error)
        # Se vuelve a mostrar con lo elegido: el paquete no se guarda en ningún lado.
        return self.render_to_response(self.get_context_data(form=form))

    def _pdf(self, cotizacion):
        respuesta = HttpResponse(pdf_cotizacion(cotizacion), content_type='application/pdf')
        respuesta['Content-Disposition'] = f'attachment; filename="{nombre_cotizacion(cotizacion)}"'
        respuesta['Cache-Control'] = 'no-store'
        return respuesta

    def _enviar(self, form, cotizacion):
        datos = form.cleaned_data
        destinos = destinos_para(
            paciente=datos['paciente'], correo=datos['correo'], whatsapp=datos['whatsapp']
        )
        fallidos = enviar_cotizacion(cotizacion, destinos)
        enviados = [d for c, d in destinos.items() if c not in fallidos]
        if enviados:
            messages.success(self.request, f'Cotización enviada a {" y ".join(enviados)}.')
        for nombre, error in fallidos.items():
            messages.error(
                self.request,
                f'No se pudo enviar por {Canal(nombre).label} a {destinos[nombre]}: {error}. '
                'Puede intentarlo de nuevo o descargar el PDF.',
            )

    def get_context_data(self, form, **kwargs):
        paciente = form['paciente'].value()
        elegido = None
        if str(paciente or '').isdigit():
            elegido = form.fields['paciente'].queryset.filter(pk=paciente).first()
        elegidos = {str(v) for v in (form['estudios'].value() or [])}
        estudios = list(form.fields['estudios'].queryset.order_by('categoria__nombre', 'nombre'))
        renglones = [e for e in estudios if str(e.pk) in elegidos]
        return super().get_context_data(
            form=form,
            estudios=estudios,
            elegidos=elegidos,
            renglones=renglones,
            total=sum(e.precio for e in renglones),
            paciente_elegido=elegido,
            destinos=destinos_para(paciente=elegido) if elegido else {},
            **kwargs,
        )
