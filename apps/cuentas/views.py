from django.contrib import messages
from django.contrib.auth.views import LoginView, LogoutView
from django.core.exceptions import ValidationError
from django.shortcuts import redirect
from django.utils import timezone
from django.views.generic import FormView, TemplateView

from apps.citas.selectors import citas_del_dia
from apps.core.forms import aplicar_errores
from apps.core.mixins import RolRequerido
from apps.cuentas.forms import FormularioEntrar, UsuarioForm
from apps.cuentas.models import Rol
from apps.cuentas.selectors import listar_usuarios
from apps.cuentas.services import registrar_usuario


class EntrarView(LoginView):
    template_name = 'cuentas/entrar.html'
    authentication_form = FormularioEntrar
    redirect_authenticated_user = True


class SalirView(LogoutView):
    pass


class InicioView(RolRequerido, TemplateView):
    template_name = 'cuentas/inicio.html'
    roles = tuple(Rol)

    def get_context_data(self, **kwargs):
        usuario = self.request.user
        if usuario.tiene_rol(Rol.RECEPCIONISTA):
            kwargs['citas_hoy'] = citas_del_dia(timezone.localdate())
        return super().get_context_data(rol=usuario.rol_principal, **kwargs)


class UsuarioListaView(RolRequerido, TemplateView):
    roles = [Rol.ADMIN]
    template_name = 'cuentas/usuarios.html'

    def get_context_data(self, **kwargs):
        return super().get_context_data(usuarios=listar_usuarios(), **kwargs)


class UsuarioCrearView(RolRequerido, FormView):
    roles = [Rol.ADMIN]
    form_class = UsuarioForm
    template_name = 'cuentas/usuario_formulario.html'

    def form_valid(self, form):
        try:
            usuario = registrar_usuario(**form.datos_servicio())
        except ValidationError as error:
            aplicar_errores(form, error)
            return self.form_invalid(form)
        messages.success(self.request, f'Usuario registrado: {usuario.correo}.')
        return redirect('cuentas:usuarios')
