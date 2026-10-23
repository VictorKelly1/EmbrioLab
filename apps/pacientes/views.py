from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import FormView, TemplateView

from apps.citas.selectors import citas_de_paciente
from apps.core.forms import aplicar_errores
from apps.core.mixins import RolRequerido
from apps.core.services import dar_de_baja, reactivar
from apps.cuentas.models import Rol
from apps.pacientes.forms import DoctorForm, PacienteForm
from apps.pacientes.models import Doctor, Paciente
from apps.pacientes.selectors import buscar_doctores, buscar_pacientes, obtener_paciente
from apps.pacientes.services import (
    actualizar_doctor,
    actualizar_paciente,
    crear_doctor,
    registrar_paciente,
)
from apps.pedidos.selectors import historial_de_paciente
from apps.personas.selectors import contactos_principales

POR_PAGINA = 25


class PacienteListaView(RolRequerido, TemplateView):
    roles = [Rol.RECEPCIONISTA, Rol.QUIMICO]
    template_name = 'pacientes/lista.html'

    def get_template_names(self):
        # La búsqueda con HTMX solo reemplaza los resultados.
        if self.request.headers.get('HX-Request'):
            return ['pacientes/_resultados.html']
        return [self.template_name]

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        termino = self.request.GET.get('q', '').strip()
        incluir_inactivos = self.request.GET.get('inactivos') == '1'
        pacientes = buscar_pacientes(termino, incluir_inactivos=incluir_inactivos)
        contexto.update(
            termino=termino,
            incluir_inactivos=incluir_inactivos,
            pagina=Paginator(pacientes, POR_PAGINA).get_page(self.request.GET.get('pagina')),
            puede_editar=self.request.user.tiene_rol(Rol.RECEPCIONISTA),
        )
        return contexto


HISTORIAL_MAXIMO = 20


class PacienteDetalleView(RolRequerido, TemplateView):
    roles = [Rol.RECEPCIONISTA, Rol.QUIMICO]
    template_name = 'pacientes/detalle.html'

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        try:
            paciente = obtener_paciente(self.kwargs['pk'])
        except Paciente.DoesNotExist as error:
            raise Http404 from error
        es_recepcion = self.request.user.tiene_rol(Rol.RECEPCIONISTA)
        contexto.update(
            paciente=paciente,
            contactos=contactos_principales(paciente.persona),
            puede_editar=es_recepcion,
            citas=citas_de_paciente(paciente)[:10] if es_recepcion else None,
            historial=historial_de_paciente(paciente)[:HISTORIAL_MAXIMO],
            historial_maximo=HISTORIAL_MAXIMO,
        )
        return contexto


class _PacienteFormView(RolRequerido, FormView):
    roles = [Rol.RECEPCIONISTA]
    form_class = PacienteForm
    template_name = 'pacientes/formulario.html'
    paciente = None

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['tiene_foto'] = bool(self.paciente and self.paciente.persona.foto)
        return kwargs

    def get_context_data(self, **kwargs):
        return super().get_context_data(paciente=self.paciente, **kwargs)

    def form_valid(self, form):
        try:
            self.paciente = self.guardar(**form.datos_servicio())
        except ValidationError as error:
            aplicar_errores(form, error)
            return self.form_invalid(form)
        messages.success(self.request, self.mensaje_exito)
        return redirect('pacientes:detalle', pk=self.paciente.pk)


class PacienteCrearView(_PacienteFormView):
    mensaje_exito = 'Paciente registrado.'

    def guardar(self, **datos):
        return registrar_paciente(**datos)


class PacienteEditarView(_PacienteFormView):
    mensaje_exito = 'Cambios guardados.'

    def dispatch(self, request, *args, **kwargs):
        self.paciente = get_object_or_404(
            Paciente.objects.select_related('persona'), pk=kwargs['pk']
        )
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        return PacienteForm.inicial_de(self.paciente)

    def guardar(self, **datos):
        return actualizar_paciente(self.paciente, **datos)


class PacienteBajaView(RolRequerido, View):
    roles = [Rol.RECEPCIONISTA]
    http_method_names = ['post']

    def post(self, request, pk):
        paciente = get_object_or_404(Paciente, pk=pk)
        if request.POST.get('accion') == 'reactivar':
            reactivar(paciente)
            messages.success(request, 'El paciente está activo de nuevo.')
        else:
            dar_de_baja(paciente)
            messages.success(request, 'El paciente quedó dado de baja. Su historial se conserva.')
        return redirect('pacientes:detalle', pk=pk)


# Doctores


class DoctorListaView(RolRequerido, TemplateView):
    roles = [Rol.RECEPCIONISTA]
    template_name = 'pacientes/doctores.html'

    def get_template_names(self):
        if self.request.headers.get('HX-Request'):
            return ['pacientes/_doctores_resultados.html']
        return [self.template_name]

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        termino = self.request.GET.get('q', '').strip()
        contexto.update(
            termino=termino,
            pagina=Paginator(buscar_doctores(termino), POR_PAGINA).get_page(
                self.request.GET.get('pagina')
            ),
        )
        return contexto


class _DoctorFormView(RolRequerido, FormView):
    roles = [Rol.RECEPCIONISTA]
    form_class = DoctorForm
    template_name = 'pacientes/doctor_formulario.html'
    doctor = None

    def get_context_data(self, **kwargs):
        return super().get_context_data(doctor=self.doctor, **kwargs)

    def form_valid(self, form):
        try:
            self.guardar(**form.cleaned_data)
        except ValidationError as error:
            aplicar_errores(form, error)
            return self.form_invalid(form)
        messages.success(self.request, self.mensaje_exito)
        return redirect('pacientes:doctores')


class DoctorCrearView(_DoctorFormView):
    mensaje_exito = 'Doctor registrado.'

    def guardar(self, **datos):
        return crear_doctor(**datos)


class DoctorEditarView(_DoctorFormView):
    mensaje_exito = 'Cambios guardados.'

    def dispatch(self, request, *args, **kwargs):
        self.doctor = get_object_or_404(Doctor, pk=kwargs['pk'])
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        return {'nombre': self.doctor.nombre, 'contacto': self.doctor.contacto}

    def guardar(self, **datos):
        return actualizar_doctor(self.doctor, **datos)
