from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ImproperlyConfigured, PermissionDenied


class RolRequerido(LoginRequiredMixin):
    """
    Restringe una vista a ciertos roles. Va en CADA vista (CONTEXTO.md §5).

        class AgendaView(RolRequerido, TemplateView):
            roles = [Rol.RECEPCIONISTA]

    Sin sesión redirige al login; con sesión pero sin el rol responde 403.
    Los controles por objeto se hacen aparte, en la vista o el selector.

    El objeto de la URL se carga en `cargar()`, que corre DESPUÉS de revisar la sesión y
    el rol: así quien no tiene permiso recibe lo mismo exista o no el objeto (no puede
    adivinar ids) y no se consulta la BD antes de tiempo. No sobrescriba `dispatch`
    para cargar objetos.
    """

    roles = ()

    def dispatch(self, request, *args, **kwargs):
        if not self.roles:
            raise ImproperlyConfigured(f'{type(self).__name__} debe definir `roles`.')
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not request.user.tiene_rol(*self.roles):
            raise PermissionDenied
        self.cargar()
        return super().dispatch(request, *args, **kwargs)

    def cargar(self) -> None:
        """Carga lo que la vista necesita de la URL (self.kwargs, self.request)."""
