"""
Menú lateral por rol. Cada opción dice qué roles la ven y en qué pantallas queda marcada.

Las opciones sin `ruta` son de semanas posteriores del plan: se muestran como "Pronto"
para que el personal conozca la estructura. Al implementarlas basta con ponerles su ruta.
"""

from dataclasses import dataclass

from django.urls import reverse

from apps.cuentas.models import Rol


@dataclass(frozen=True)
class Opcion:
    etiqueta: str
    icono: str
    roles: tuple[str, ...]
    ruta: str | None = None
    # Prefijos de nombres de vista ('app:vista') en los que la opción queda activa.
    activa_en: tuple[str, ...] = ()


RECEPCION = (Rol.RECEPCIONISTA,)
QUIMICO = (Rol.QUIMICO,)
TODOS = tuple(Rol)

OPCIONES = (
    Opcion('Inicio', 'inicio', TODOS, 'inicio', ('inicio',)),
    Opcion('Calendario de citas', 'calendario', RECEPCION, 'citas:calendario', ('citas:',)),
    Opcion('Pedidos', 'pedidos', RECEPCION + QUIMICO),
    Opcion(
        'Pacientes',
        'pacientes',
        RECEPCION + QUIMICO,
        'pacientes:lista',
        (
            'pacientes:lista',
            'pacientes:crear',
            'pacientes:detalle',
            'pacientes:editar',
        ),
    ),
    Opcion('Formularios', 'formularios', RECEPCION, 'formularios:lista', ('formularios:',)),
    Opcion(
        'Catálogo de estudios', 'estudios', RECEPCION + QUIMICO, 'estudios:lista', ('estudios:',)
    ),
    Opcion('Doctores', 'doctores', RECEPCION, 'pacientes:doctores', ('pacientes:doctor',)),
    Opcion('Usuarios', 'usuarios', (Rol.ADMIN,), 'cuentas:usuarios', ('cuentas:usuario',)),
    Opcion('Reportes', 'reportes', (Rol.ADMIN,)),
)


def opciones_para(usuario, vista_actual: str = '') -> list[dict]:
    """Opciones visibles para el usuario, con su URL y si corresponden a la vista actual."""
    roles = usuario.roles
    menu = []
    for opcion in OPCIONES:
        if not roles.intersection(opcion.roles):
            continue
        menu.append(
            {
                'etiqueta': opcion.etiqueta,
                'icono': opcion.icono,
                'url': reverse(opcion.ruta) if opcion.ruta else None,
                'activa': any(vista_actual.startswith(p) for p in opcion.activa_en),
            }
        )
    return menu


def menu(request):
    """Context processor: `menu_lateral` para las pantallas con sesión."""
    if not getattr(request, 'user', None) or not request.user.is_authenticated:
        return {}
    coincidencia = request.resolver_match
    vista = coincidencia.view_name if coincidencia else ''
    opciones = opciones_para(request.user, vista)
    return {
        'menu_lateral': [o for o in opciones if o['url']],
        'menu_lateral_pronto': [o for o in opciones if not o['url']],
    }
