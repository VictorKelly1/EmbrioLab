from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.generic import TemplateView

from apps.citas.models import Cita, EstadoCita
from apps.core.forms import aplicar_errores
from apps.core.mixins import RolRequerido
from apps.cuentas.models import Rol
from apps.estudios.selectors import referencias_para, sugerir_estudios
from apps.formularios.selectors import respuestas_de
from apps.notificaciones.selectors import notificaciones_de_pedido
from apps.notificaciones.services import destinatarios, destinatarios_doctor
from apps.pacientes.models import Paciente
from apps.pedidos.forms import (
    DoctorPedidoForm,
    EnviarResultadosForm,
    EstudioPedidoForm,
    FiltroPedidosForm,
    LineaForm,
    LineaFormSet,
    ObservacionForm,
    PagoPedidoForm,
    ReasignarForm,
    ResultadosForm,
)
from apps.pedidos.models import EstadoEstudio, EstadoPedido, EstudioPedido, Pedido
from apps.pedidos.resultados import filas
from apps.pedidos.selectors import (
    buscar_pedidos,
    cola_por_paciente,
    estudios_completados,
    historial_de_paciente,
    obtener_estudio_pedido,
    obtener_pedido,
    toma_del_paciente,
)
from apps.pedidos.services import (
    agregar_estudio,
    agregar_observacion,
    cambiar_doctor,
    cambiar_estado_pago,
    cambiar_pago_pedido,
    completar_estudio,
    crear_pedido,
    enviar_resultados,
    guardar_borrador,
    pasar_paciente,
    quitar_estudio,
    soltar_paciente,
    tomar_paciente,
)

POR_PAGINA = 25


def _mensaje(error: ValidationError) -> str:
    return ' '.join(error.messages)


class PedidoListaView(RolRequerido, TemplateView):
    roles = [Rol.RECEPCIONISTA, Rol.QUIMICO]
    template_name = 'pedidos/lista.html'

    def get_template_names(self):
        if self.request.headers.get('HX-Request'):
            return ['pedidos/_resultados.html']
        return [self.template_name]

    def get_context_data(self, **kwargs):
        filtros = FiltroPedidosForm(self.request.GET)
        datos = filtros.cleaned_data if filtros.is_valid() else {}
        pedidos = buscar_pedidos(
            datos.get('q', ''),
            estado=datos.get('estado', ''),
            estado_pago=datos.get('estado_pago', ''),
            quimico=datos.get('quimico'),
            desde=datos.get('desde'),
            hasta=datos.get('hasta'),
        )
        usuario = self.request.user
        es_quimico = usuario.tiene_rol(Rol.QUIMICO)
        return super().get_context_data(
            filtros=filtros,
            filtrado=any(datos.values()),
            es_quimico=es_quimico,
            mio=usuario.quimico.pk if es_quimico and not datos.get('quimico') else None,
            pagina=Paginator(pedidos, POR_PAGINA).get_page(self.request.GET.get('pagina')),
            **kwargs,
        )


class PedidoCrearView(RolRequerido, TemplateView):
    """Se arma desde una cita atendida: `?cita=<pk>`."""

    roles = [Rol.RECEPCIONISTA]
    template_name = 'pedidos/crear.html'

    def get(self, request, *args, **kwargs):
        if respuesta := self._cargar_cita():
            return respuesta
        return self.render_to_response(
            self.get_context_data(form=DoctorPedidoForm(), lineas=LineaFormSet())
        )

    def _cargar_cita(self):
        """Carga la cita; si no está atendida, regresa a ella con el aviso."""
        pk = self.request.GET.get('cita', '')
        if not pk.isdigit():
            raise Http404
        self.cita = get_object_or_404(Cita.objects.select_related('paciente__persona'), pk=pk)
        if self.cita.estado != EstadoCita.ATENDIDA:
            messages.error(self.request, 'Marque la cita como atendida antes de armar su pedido.')
            return redirect('citas:detalle', pk=self.cita.pk)
        return None

    def post(self, request, *args, **kwargs):
        if respuesta := self._cargar_cita():
            return respuesta
        form = DoctorPedidoForm(request.POST)
        lineas = LineaFormSet(request.POST)
        if form.is_valid() and lineas.is_valid():
            try:
                pedido = crear_pedido(
                    cita=self.cita,
                    recepcionista=request.user.recepcionista,
                    doctor=form.cleaned_data['doctor'],
                    lineas=[f.linea() for f in lineas if f.has_changed()],
                )
            except ValidationError as error:
                aplicar_errores(form, error)
            else:
                messages.success(request, f'Pedido {pedido.numero} creado.')
                return redirect('pedidos:detalle', pk=pedido.pk)
        return self.render_to_response(self.get_context_data(form=form, lineas=lineas))

    def get_context_data(self, **kwargs):
        return super().get_context_data(cita=self.cita, **kwargs)


class SugerenciasView(RolRequerido, TemplateView):
    """Fragmento HTMX: estudios que se parecen al nombre de la orden."""

    roles = [Rol.RECEPCIONISTA]
    template_name = 'pedidos/_sugerencias.html'

    def get_context_data(self, **kwargs):
        # El campo se llama `form-0-nombre_solicitado`, `nuevo-nombre_solicitado`, etc.
        texto = next(
            (v for k, v in self.request.GET.items() if k.endswith('nombre_solicitado')), ''
        )
        return super().get_context_data(
            buscado=len(texto.strip()) >= 2, sugerencias=sugerir_estudios(texto), **kwargs
        )


class PedidoDetalleView(RolRequerido, TemplateView):
    roles = [Rol.RECEPCIONISTA, Rol.QUIMICO]
    template_name = 'pedidos/detalle.html'

    def get_context_data(self, **kwargs):
        try:
            pedido = obtener_pedido(self.kwargs['pk'])
        except Pedido.DoesNotExist as error:
            raise Http404 from error
        usuario = self.request.user
        puede_editar = usuario.tiene_rol(Rol.RECEPCIONISTA)
        quimico = usuario.quimico if usuario.tiene_rol(Rol.QUIMICO) else None
        estudios = list(pedido.estudios.all())
        for estudio in estudios:
            estudio.completado = estudio.estado == EstadoEstudio.COMPLETADO
            estudio.puede_capturar = _puede_capturar(estudio, quimico)
            estudio.puede_corregir = _puede_corregir(estudio, quimico)
            if puede_editar:
                estudio.form = EstudioPedidoForm(
                    prefix=f'fila{estudio.pk}', initial={'estado_pago': estudio.estado_pago}
                )
                # El select va en la tabla y el <form> en la última celda.
                for campo in estudio.form.fields.values():
                    campo.widget.attrs['form'] = f'fila-{estudio.pk}'
        abierto = pedido.estado != EstadoPedido.COMPLETADO
        llenado = getattr(pedido.cita, 'formulario_llenado', None)
        completados = estudios_completados(pedido)
        return super().get_context_data(
            pedido=pedido,
            estudios=estudios,
            **_contexto_toma(pedido.cita.paciente, quimico),
            hay_completados=any(e.completado for e in estudios),
            enviar_form=(
                EnviarResultadosForm(completados=completados) if quimico is not None else None
            ),
            destinos=destinatarios(pedido.cita.paciente.persona),
            destinos_doctor=destinatarios_doctor(pedido.doctor),
            notificaciones=notificaciones_de_pedido(pedido),
            llenado=llenado,
            respuestas=respuestas_de(llenado) if llenado else None,
            puede_editar=puede_editar,
            puede_quitar=puede_editar and len(estudios) > 1,
            doctor_form=DoctorPedidoForm(initial={'doctor': pedido.doctor}),
            observacion_form=ObservacionForm() if puede_editar else None,
            agregar_form=LineaForm(prefix='nuevo') if puede_editar and abierto else None,
            **kwargs,
        )


def _puede_capturar(estudio_pedido, quimico) -> bool:
    """El control por objeto de la captura; el servicio lo vuelve a revisar."""
    return (
        quimico is not None
        and estudio_pedido.estado == EstadoEstudio.EN_PROCESO
        and estudio_pedido.quimico_encargado_id == quimico.pk
    )


def _puede_corregir(estudio_pedido, quimico) -> bool:
    """Su encargado corrige un completado mientras no se envíe (CONTEXTO.md §3)."""
    return (
        quimico is not None
        and estudio_pedido.estado == EstadoEstudio.COMPLETADO
        and not estudio_pedido.enviado
        and estudio_pedido.quimico_encargado_id == quimico.pk
    )


def _contexto_toma(paciente, quimico) -> dict:
    """Quién tiene al paciente y los botones de tomar, soltar y pasar (CONTEXTO.md §3)."""
    toma = toma_del_paciente(paciente, quimico)
    return {
        'toma': toma,
        'pasar_form': ReasignarForm(quimico=quimico) if toma.puede_soltar else None,
    }


class EstudioPedidoResultadosView(RolRequerido, TemplateView):
    """
    Resultados de un estudio. Su químico encargado los captura mientras está en proceso
    (borrador o completar); los demás solo los ven.
    """

    roles = [Rol.RECEPCIONISTA, Rol.QUIMICO]
    template_name = 'pedidos/resultados.html'

    def _cargar(self):
        """Después de RolRequerido: sin el rol responde 403 antes de buscar el estudio."""
        try:
            self.estudio_pedido = obtener_estudio_pedido(self.kwargs['pk'])
        except EstudioPedido.DoesNotExist as error:
            raise Http404 from error
        self.definicion = self.estudio_pedido.estudio.definicion
        usuario = self.request.user
        self.quimico = usuario.quimico if usuario.tiene_rol(Rol.QUIMICO) else None
        self.puede_capturar = self.definicion is not None and _puede_capturar(
            self.estudio_pedido, self.quimico
        )
        self.puede_corregir = self.definicion is not None and _puede_corregir(
            self.estudio_pedido, self.quimico
        )
        # Un completado muestra sus resultados; el formulario solo si se pide corregir.
        self.corrigiendo = self.puede_corregir and (
            self.request.GET.get('corregir') or self.request.method == 'POST'
        )

    def get(self, request, *args, **kwargs):
        self._cargar()
        form = None
        if self.puede_capturar or self.corrigiendo:
            guardados = (self.estudio_pedido.resultados or {}).get('valores', {})
            form = ResultadosForm(
                definicion=self.definicion, initial=self.definicion.de_json(guardados)
            )
        return self.render_to_response(self.get_context_data(form=form))

    def _con_referencias(self, form):
        """Muestra junto a cada campo la referencia que se copiará al completar."""
        cita = self.estudio_pedido.pedido.cita
        referencias = referencias_para(
            self.estudio_pedido.estudio, cita.paciente, timezone.localdate(cita.fecha_hora)
        )
        for clave, referencia in referencias.items():
            if clave in form.fields:
                form.fields[clave].help_text = f'Referencia: {referencia.rango}'
        return form

    def post(self, request, *args, **kwargs):
        self._cargar()
        if not (self.puede_capturar or self.corrigiendo):
            raise PermissionDenied
        # Al corregir solo se puede volver a completar: un completado no regresa a borrador.
        completar = self.corrigiendo or request.POST.get('accion') == 'completar'
        form = ResultadosForm(request.POST, definicion=self.definicion, completar=completar)
        if form.is_valid():
            servicio = completar_estudio if completar else guardar_borrador
            try:
                servicio(self.estudio_pedido, form.valores(), quimico=self.quimico)
            except ValidationError as error:
                aplicar_errores(form, error)
            else:
                if self.corrigiendo:
                    messages.success(request, f'{self.estudio_pedido.estudio} corregido.')
                    return redirect('pedidos:resultados', pk=self.estudio_pedido.pk)
                if completar:
                    messages.success(request, f'{self.estudio_pedido.estudio} completado.')
                    return redirect('pedidos:detalle', pk=self.estudio_pedido.pedido_id)
                messages.success(request, 'Borrador guardado. El estudio sigue en proceso.')
                return redirect('pedidos:resultados', pk=self.estudio_pedido.pk)
        return self.render_to_response(self.get_context_data(form=form))

    def get_context_data(self, form=None, **kwargs):
        if form is not None:
            self._con_referencias(form)
        estudio_pedido = self.estudio_pedido
        paciente = estudio_pedido.pedido.cita.paciente
        anteriores = historial_de_paciente(
            paciente, estudio=estudio_pedido.estudio, excluir=estudio_pedido
        )[:5]
        for anterior in anteriores:
            anterior.filas = filas(anterior)
        return super().get_context_data(
            estudio_pedido=estudio_pedido,
            pedido=estudio_pedido.pedido,
            paciente=paciente,
            definicion=self.definicion,
            **_contexto_toma(paciente, self.quimico),
            completado=estudio_pedido.estado == EstadoEstudio.COMPLETADO,
            puede_corregir=self.puede_corregir,
            corrigiendo=self.corrigiendo,
            calculados=self.definicion.calculados if self.definicion else (),
            filas=filas(estudio_pedido),
            anteriores=anteriores,
            form=form,
            **kwargs,
        )


class ColaView(RolRequerido, TemplateView):
    """Los estudios sin encargado, agrupados por pedido, para que un químico los tome."""

    roles = [Rol.QUIMICO]
    template_name = 'pedidos/cola.html'

    def get_context_data(self, **kwargs):
        return super().get_context_data(pacientes=cola_por_paciente(), **kwargs)


class _AccionPedidoView(RolRequerido, View):
    """POST desde el detalle: llama a un servicio y vuelve al detalle con un mensaje."""

    roles = [Rol.RECEPCIONISTA]
    http_method_names = ['post']

    def post(self, request, pk):
        objeto = get_object_or_404(self.modelo, pk=pk)
        try:
            mensaje = self.ejecutar(objeto)
        except ValidationError as error:
            messages.error(request, _mensaje(error))
        else:
            if mensaje:
                messages.success(request, mensaje)
        # Desde la cola se vuelve a la cola; cualquier otro valor regresa al pedido.
        if request.POST.get('volver') == 'cola':
            return redirect('pedidos:cola')
        pedido_pk = objeto.pk if isinstance(objeto, Pedido) else objeto.pedido_id
        return redirect('pedidos:detalle', pk=pedido_pk)

    def _form(self, clase, **kwargs):
        form = clase(self.request.POST, **kwargs)
        if not form.is_valid():
            raise ValidationError(
                [e for errores in form.errors.values() for e in errores] or 'Datos no válidos.'
            )
        return form


class PedidoDoctorView(_AccionPedidoView):
    modelo = Pedido

    def ejecutar(self, pedido):
        cambiar_doctor(pedido, self._form(DoctorPedidoForm).cleaned_data['doctor'])
        return 'Doctor actualizado.'


class PedidoObservacionView(_AccionPedidoView):
    modelo = Pedido

    def ejecutar(self, pedido):
        texto = self._form(ObservacionForm).cleaned_data['texto']
        agregar_observacion(pedido, texto, usuario=self.request.user)
        return 'Observación agregada.'


class PedidoPagoView(_AccionPedidoView):
    modelo = Pedido

    def ejecutar(self, pedido):
        estado = self._form(PagoPedidoForm).cleaned_data['estado_pago']
        cambiar_pago_pedido(pedido, estado)
        return 'Pago actualizado en todos los estudios.'


class PedidoAgregarEstudioView(_AccionPedidoView):
    modelo = Pedido

    def ejecutar(self, pedido):
        linea = self._form(LineaForm, prefix='nuevo').linea()
        agregar_estudio(pedido, linea, usuario=self.request.user)
        return f'Se agregó {linea.estudio}.'


class EstudioPedidoActualizarView(_AccionPedidoView):
    modelo = EstudioPedido

    def ejecutar(self, estudio_pedido):
        datos = self._form(EstudioPedidoForm, prefix=f'fila{estudio_pedido.pk}').cleaned_data
        if datos['estado_pago'] == estudio_pedido.estado_pago:
            return None
        cambiar_estado_pago(estudio_pedido, datos['estado_pago'])
        return 'Pago actualizado.'


class _AccionPacienteView(RolRequerido, View):
    """
    Tomar, soltar o pasar a un paciente con todos sus estudios (CONTEXTO.md §3).
    Vuelve a la pantalla de origen (`siguiente`) o a la cola.
    """

    roles = [Rol.QUIMICO]
    http_method_names = ['post']

    def post(self, request, pk):
        paciente = get_object_or_404(Paciente.objects.select_related('persona'), pk=pk)
        quimico = request.user.quimico
        try:
            mensaje = self.ejecutar(paciente, quimico)
        except ValidationError as error:
            messages.error(request, _mensaje(error))
        else:
            messages.success(request, mensaje)
        siguiente = request.POST.get('siguiente', '')
        if url_has_allowed_host_and_scheme(
            siguiente, allowed_hosts={request.get_host()}, require_https=request.is_secure()
        ):
            return redirect(siguiente)
        return redirect('pedidos:cola')


def _cuantos(estudios) -> str:
    return f'{len(estudios)} estudio{"" if len(estudios) == 1 else "s"}'


class PacienteTomarView(_AccionPacienteView):
    def ejecutar(self, paciente, quimico):
        estudios = tomar_paciente(paciente, quimico=quimico)
        return (
            f'{paciente.persona.nombre_completo} quedó a su cargo con {_cuantos(estudios)}. '
            'Aparecen en su lista de trabajo.'
        )


class PacienteSoltarView(_AccionPacienteView):
    def ejecutar(self, paciente, quimico):
        estudios = soltar_paciente(paciente, quimico=quimico)
        return f'{paciente.persona.nombre_completo} regresó a la cola con {_cuantos(estudios)}.'


class PacientePasarView(_AccionPacienteView):
    def ejecutar(self, paciente, quimico):
        form = ReasignarForm(self.request.POST, quimico=quimico)
        if not form.is_valid():
            raise ValidationError(
                [e for errores in form.errors.values() for e in errores] or 'Datos no válidos.'
            )
        nuevo = form.cleaned_data['quimico']
        pasar_paciente(paciente, nuevo, quimico=quimico)
        return (
            f'{paciente.persona.nombre_completo} quedó a cargo de '
            f'{nuevo.usuario.persona.nombre_completo}.'
        )


class EstudioPedidoQuitarView(_AccionPedidoView):
    modelo = EstudioPedido

    def ejecutar(self, estudio_pedido):
        quitar_estudio(estudio_pedido)
        return f'Se quitó {estudio_pedido.estudio}.'


class PedidoEnviarResultadosView(_AccionPedidoView):
    """El químico envía al paciente uno o varios estudios completados (CONTEXTO.md §2)."""

    roles = [Rol.QUIMICO]
    modelo = Pedido

    def ejecutar(self, pedido):
        form = self._form(EnviarResultadosForm, completados=estudios_completados(pedido))
        al_doctor = form.cleaned_data['al_doctor'] and bool(destinatarios_doctor(pedido.doctor))
        estudios = enviar_resultados(
            form.cleaned_data['estudios'], usuario=self.request.user, al_doctor=al_doctor
        )
        cuantos = len(estudios)
        return (
            f'Se {"enviará" if cuantos == 1 else "enviarán"} {cuantos} '
            f'estudio{"" if cuantos == 1 else "s"} al paciente'
            f'{" y al doctor" if al_doctor else ""}. El estado de cada envío aparece abajo.'
        )
