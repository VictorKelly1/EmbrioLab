from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from apps.citas.models import Cita, EstadoCita
from apps.core.forms import aplicar_errores
from apps.core.mixins import RolRequerido
from apps.cuentas.models import Rol
from apps.estudios.selectors import referencias_para, sugerir_estudios
from apps.formularios.selectors import respuestas_de
from apps.pedidos.forms import (
    DoctorPedidoForm,
    EstudioPedidoForm,
    FiltroPedidosForm,
    LineaForm,
    LineaFormSet,
    PagoPedidoForm,
    ResultadosForm,
)
from apps.pedidos.models import EstadoEstudio, EstadoPedido, EstudioPedido, Pedido
from apps.pedidos.resultados import filas
from apps.pedidos.selectors import (
    buscar_pedidos,
    historial_de_paciente,
    obtener_estudio_pedido,
    obtener_pedido,
)
from apps.pedidos.services import (
    actualizar_estudio_pedido,
    agregar_estudio,
    cambiar_doctor,
    cambiar_pago_pedido,
    completar_estudio,
    crear_pedido,
    guardar_borrador,
    quitar_estudio,
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
            estudio.quimicos = list(estudio.quimicos_asignados.all())
            estudio.puede_capturar = _puede_capturar(estudio, quimico, estudio.quimicos)
            if puede_editar:
                estudio.form = EstudioPedidoForm(
                    prefix=f'fila{estudio.pk}',
                    quimicos_asignados=estudio.quimicos,
                    initial={'quimicos': estudio.quimicos, 'estado_pago': estudio.estado_pago},
                )
                # Los selects van en la tabla y el <form> en la última celda.
                for campo in estudio.form.fields.values():
                    campo.widget.attrs['form'] = f'fila-{estudio.pk}'
        abierto = pedido.estado != EstadoPedido.COMPLETADO
        llenado = getattr(pedido.cita, 'formulario_llenado', None)
        return super().get_context_data(
            pedido=pedido,
            estudios=estudios,
            llenado=llenado,
            respuestas=respuestas_de(llenado) if llenado else None,
            puede_editar=puede_editar,
            puede_quitar=puede_editar and len(estudios) > 1,
            doctor_form=DoctorPedidoForm(initial={'doctor': pedido.doctor}),
            agregar_form=LineaForm(prefix='nuevo') if puede_editar and abierto else None,
            **kwargs,
        )


def _puede_capturar(estudio_pedido, quimico, quimicos_asignados) -> bool:
    """El control por objeto de la captura; el servicio lo vuelve a revisar."""
    return (
        quimico is not None
        and estudio_pedido.estado == EstadoEstudio.EN_PROCESO
        and quimico in quimicos_asignados
    )


class EstudioPedidoResultadosView(RolRequerido, TemplateView):
    """
    Resultados de un estudio. Un químico asignado los captura mientras está en proceso
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
        self.quimicos = list(self.estudio_pedido.quimicos_asignados.all())
        self.puede_capturar = self.definicion is not None and _puede_capturar(
            self.estudio_pedido, self.quimico, self.quimicos
        )

    def get(self, request, *args, **kwargs):
        self._cargar()
        form = None
        if self.puede_capturar:
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
        if not self.puede_capturar:
            raise PermissionDenied
        completar = request.POST.get('accion') == 'completar'
        form = ResultadosForm(request.POST, definicion=self.definicion, completar=completar)
        if form.is_valid():
            servicio = completar_estudio if completar else guardar_borrador
            try:
                servicio(self.estudio_pedido, form.valores(), quimico=self.quimico)
            except ValidationError as error:
                aplicar_errores(form, error)
            else:
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
            quimicos=self.quimicos,
            completado=estudio_pedido.estado == EstadoEstudio.COMPLETADO,
            calculados=self.definicion.calculados if self.definicion else (),
            filas=filas(estudio_pedido),
            anteriores=anteriores,
            form=form,
            **kwargs,
        )


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
        datos = self._form(
            EstudioPedidoForm,
            prefix=f'fila{estudio_pedido.pk}',
            quimicos_asignados=estudio_pedido.quimicos_asignados.all(),
        ).cleaned_data
        actualizar_estudio_pedido(
            estudio_pedido,
            quimicos=list(datos['quimicos']),
            estado_pago=datos['estado_pago'],
            usuario=self.request.user,
        )
        return 'Cambios guardados.'


class EstudioPedidoQuitarView(_AccionPedidoView):
    modelo = EstudioPedido

    def ejecutar(self, estudio_pedido):
        quitar_estudio(estudio_pedido)
        return f'Se quitó {estudio_pedido.estudio}.'
