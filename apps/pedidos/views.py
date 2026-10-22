from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import TemplateView

from apps.citas.models import Cita, EstadoCita
from apps.core.forms import aplicar_errores
from apps.core.mixins import RolRequerido
from apps.cuentas.models import Rol
from apps.estudios.selectors import sugerir_estudios
from apps.pedidos.forms import (
    DoctorPedidoForm,
    EstudioPedidoForm,
    FiltroPedidosForm,
    LineaForm,
    LineaFormSet,
    PagoPedidoForm,
)
from apps.pedidos.models import EstadoEstudio, EstadoPedido, EstudioPedido, Pedido
from apps.pedidos.selectors import buscar_pedidos, obtener_pedido
from apps.pedidos.services import (
    actualizar_estudio_pedido,
    agregar_estudio,
    cambiar_doctor,
    cambiar_pago_pedido,
    crear_pedido,
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
        )
        return super().get_context_data(
            filtros=filtros,
            filtrado=any(datos.values()),
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
        puede_editar = self.request.user.tiene_rol(Rol.RECEPCIONISTA)
        estudios = list(pedido.estudios.all())
        for estudio in estudios:
            estudio.completado = estudio.estado == EstadoEstudio.COMPLETADO
            if puede_editar:
                estudio.form = EstudioPedidoForm(
                    prefix=f'fila{estudio.pk}',
                    initial={
                        'quimico': estudio.quimico_asignado,
                        'estado_pago': estudio.estado_pago,
                    },
                )
                # Los selects van en la tabla y el <form> en la última celda.
                for campo in estudio.form.fields.values():
                    campo.widget.attrs['form'] = f'fila-{estudio.pk}'
        abierto = pedido.estado != EstadoPedido.COMPLETADO
        return super().get_context_data(
            pedido=pedido,
            estudios=estudios,
            puede_editar=puede_editar,
            puede_quitar=puede_editar and len(estudios) > 1,
            doctor_form=DoctorPedidoForm(initial={'doctor': pedido.doctor}),
            agregar_form=LineaForm(prefix='nuevo') if puede_editar and abierto else None,
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
        datos = self._form(EstudioPedidoForm, prefix=f'fila{estudio_pedido.pk}').cleaned_data
        actualizar_estudio_pedido(
            estudio_pedido,
            quimico=datos['quimico'],
            estado_pago=datos['estado_pago'],
            usuario=self.request.user,
        )
        return 'Cambios guardados.'


class EstudioPedidoQuitarView(_AccionPedidoView):
    modelo = EstudioPedido

    def ejecutar(self, estudio_pedido):
        quitar_estudio(estudio_pedido)
        return f'Se quitó {estudio_pedido.estudio}.'
