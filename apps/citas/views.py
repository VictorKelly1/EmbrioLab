import datetime

import segno
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import formats, timezone
from django.views.generic import FormView, TemplateView

from apps.citas import calendario
from apps.citas.forms import CitaForm, EspontaneaForm, ReprogramarForm
from apps.citas.models import Cita, EstadoCita
from apps.citas.selectors import (
    citas_entre,
    obtener_cita,
    proximas_citas,
    siguiente_horario_libre,
)
from apps.citas.services import (
    agendar_cita,
    cancelar_cita,
    generar_token_qr,
    marcar_atendida,
    marcar_no_atendida,
    registrar_espontanea,
    reprogramar_cita,
)
from apps.core.forms import aplicar_errores
from apps.core.mixins import RolRequerido
from apps.cuentas.models import Rol
from apps.formularios.selectors import respuestas_de
from apps.pacientes.models import Paciente
from apps.pacientes.selectors import buscar_pacientes
from apps.pedidos.selectors import pedidos_de_cita


def _aplicar_errores_con_sugerencia(form, error: ValidationError, fecha_hora) -> None:
    """Si el horario está ocupado, sugiere el siguiente libre."""
    aplicar_errores(form, error)
    if hasattr(error, 'error_dict') and 'fecha_hora' in error.error_dict:
        libre = timezone.localtime(siguiente_horario_libre(fecha_hora))
        form.add_error(None, f'Siguiente horario libre: {libre:%d/%m/%Y a las %H:%M}.')


def _titulo_rango(dias: list[datetime.date]) -> str:
    """'miércoles 21 de octubre de 2026' o '19 – 24 de octubre de 2026'."""
    primero, ultimo = dias[0], dias[-1]
    if primero == ultimo:
        return formats.date_format(primero, r'l j \d\e F \d\e Y').lower()
    formato_inicio = 'j' if primero.month == ultimo.month else r'j \d\e F'
    inicio = formats.date_format(primero, formato_inicio)
    fin = formats.date_format(ultimo, r'j \d\e F \d\e Y')
    return f'{inicio} – {fin}'.lower()


class CalendarioView(RolRequerido, TemplateView):
    roles = [Rol.RECEPCIONISTA]
    template_name = 'citas/calendario.html'

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        vista = self.request.GET.get('vista')
        if vista not in (calendario.Vista.DIA, calendario.Vista.SEMANA):
            vista = calendario.Vista.SEMANA
        try:
            fecha = datetime.date.fromisoformat(self.request.GET.get('fecha', ''))
        except ValueError:
            fecha = timezone.localdate()

        if vista == calendario.Vista.DIA:
            dias = [fecha]
            citas = list(citas_entre(*calendario.rango(dias)))
        else:
            citas = list(citas_entre(*calendario.rango(calendario.semana_completa(fecha))))
            con_citas = {timezone.localtime(c.fecha_hora).date() for c in citas}
            dias = calendario.dias_de(fecha, vista, con_citas)
        paso = datetime.timedelta(days=1 if vista == calendario.Vista.DIA else 7)
        contexto.update(
            titulo_rango=_titulo_rango(dias),
            vista=vista,
            fecha=fecha,
            hoy=timezone.localdate(),
            dias=dias,
            filas=calendario.armar_filas(dias, citas),
            anterior=fecha - paso,
            siguiente=fecha + paso,
            proximas=proximas_citas(),
        )
        return contexto


class _CitaFormView(RolRequerido, FormView):
    roles = [Rol.RECEPCIONISTA]

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        form = contexto['form']
        paciente_id = form['paciente'].value()
        contexto['paciente_elegido'] = (
            Paciente.objects.select_related('persona').filter(pk=paciente_id).first()
            if str(paciente_id or '').isdigit()
            else None
        )
        return contexto

    def form_valid(self, form):
        fecha_hora = form.fecha_hora()
        try:
            cita = self.guardar(form.cleaned_data, fecha_hora)
        except ValidationError as error:
            _aplicar_errores_con_sugerencia(form, error, fecha_hora)
            return self.form_invalid(form)
        messages.success(self.request, self.mensaje_exito)
        return redirect('citas:detalle', pk=cita.pk)


class AgendarView(_CitaFormView):
    form_class = CitaForm
    template_name = 'citas/agendar.html'
    mensaje_exito = 'Cita agendada.'

    def get_initial(self):
        inicial = {'paciente': self.request.GET.get('paciente')}
        try:
            fecha_hora = datetime.datetime.fromisoformat(self.request.GET['fecha_hora'])
        except (KeyError, ValueError):
            fecha_hora = timezone.localtime(siguiente_horario_libre(timezone.now()))
        inicial.update(fecha=fecha_hora.date(), hora=fecha_hora.time())
        return inicial

    def guardar(self, datos, fecha_hora):
        return agendar_cita(
            recepcionista=self.request.user.recepcionista,
            paciente=datos['paciente'],
            fecha_hora=fecha_hora,
            asunto=datos['asunto'],
        )


class EspontaneaView(_CitaFormView):
    form_class = EspontaneaForm
    template_name = 'citas/espontanea.html'
    mensaje_exito = 'Paciente registrado como atendido sin cita.'

    def get_initial(self):
        return {
            'paciente': self.request.GET.get('paciente'),
            'hora': timezone.localtime().time().replace(second=0, microsecond=0),
        }

    def guardar(self, datos, fecha_hora):
        return registrar_espontanea(
            recepcionista=self.request.user.recepcionista,
            paciente=datos['paciente'],
            fecha_hora=fecha_hora,
            asunto=datos['asunto'],
        )


class BuscarPacienteView(RolRequerido, TemplateView):
    """Resultados del buscador de pacientes en los formularios de cita (HTMX)."""

    roles = [Rol.RECEPCIONISTA]
    template_name = 'citas/_buscar_paciente.html'

    def get_context_data(self, **kwargs):
        termino = self.request.GET.get('q', '').strip()
        pacientes = buscar_pacientes(termino)[:8] if len(termino) >= 2 else []
        return super().get_context_data(termino=termino, pacientes=pacientes, **kwargs)


class CitaDetalleView(RolRequerido, TemplateView):
    roles = [Rol.RECEPCIONISTA]
    template_name = 'citas/detalle.html'

    def dispatch(self, request, *args, **kwargs):
        try:
            self.cita = obtener_cita(kwargs['pk'])
        except Cita.DoesNotExist as error:
            raise Http404 from error
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        cita = self.cita
        local = timezone.localtime(cita.fecha_hora)
        kwargs.setdefault(
            'reprogramar_form',
            ReprogramarForm(initial={'fecha': local.date(), 'hora': local.time()}),
        )
        llenado = getattr(cita, 'formulario_llenado', None)
        return super().get_context_data(
            cita=cita,
            llenado=llenado,
            respuestas=respuestas_de(llenado) if llenado else None,
            pedidos=pedidos_de_cita(cita),
            atendida=cita.estado == EstadoCita.ATENDIDA,
            programada=cita.estado == EstadoCita.PROGRAMADA,
            ya_empezo=cita.fecha_hora <= timezone.now(),
            **kwargs,
        )


class ReprogramarView(CitaDetalleView):
    http_method_names = ['post']

    def post(self, request, pk):
        form = ReprogramarForm(request.POST)
        if form.is_valid():
            try:
                reprogramar_cita(self.cita, fecha_hora=form.fecha_hora())
            except ValidationError as error:
                _aplicar_errores_con_sugerencia(form, error, form.fecha_hora())
            else:
                messages.success(request, 'Cita reprogramada.')
                return redirect('citas:detalle', pk=pk)
        self.cita.refresh_from_db()
        return self.render_to_response(self.get_context_data(reprogramar_form=form))


class CitaAccionView(CitaDetalleView):
    """Marcar atendida / no atendida o cancelar."""

    http_method_names = ['post']
    acciones = {
        'atendida': (marcar_atendida, 'Cita marcada como atendida.'),
        'no_atendida': (marcar_no_atendida, 'Cita marcada como no atendida.'),
        'cancelar': (cancelar_cita, 'Cita cancelada.'),
    }

    def post(self, request, pk):
        accion = request.POST.get('accion')
        if accion not in self.acciones:
            raise Http404
        servicio, mensaje = self.acciones[accion]
        try:
            servicio(self.cita)
        except ValidationError as error:
            messages.error(request, ' '.join(error.messages))
            return redirect('citas:detalle', pk=pk)
        messages.success(request, mensaje)
        if accion == 'cancelar':
            return redirect('citas:calendario')
        return redirect('citas:detalle', pk=pk)


class GenerarQRView(CitaDetalleView):
    """
    Muestra el link y el QR una sola vez: en la BD solo queda el hash, así que no se
    pueden volver a ver; si hace falta, se genera otro (e invalida el anterior).
    """

    http_method_names = ['post']

    def post(self, request, pk):
        try:
            token = generar_token_qr(self.cita)
        except ValidationError as error:
            messages.error(request, ' '.join(error.messages))
            return redirect('citas:detalle', pk=pk)
        link = request.build_absolute_uri(reverse('formulario_publico', args=[token]))
        qr = segno.make(link, error='m').svg_inline(scale=5, dark='#2a2236', border=2)
        return self.render_to_response(self.get_context_data(link=link, qr=qr))
