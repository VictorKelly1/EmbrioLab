from django.contrib.auth.views import LoginView, LogoutView
from django.views.generic import TemplateView

from apps.core.mixins import RolRequerido
from apps.cuentas.forms import FormularioEntrar
from apps.cuentas.models import Rol


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
        contexto = super().get_context_data(**kwargs)
        roles = self.request.user.roles
        contexto['rol'] = next((Rol(r).label for r in Rol if r in roles), '')
        return contexto
