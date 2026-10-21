from django.db.models import QuerySet

from apps.cuentas.models import Usuario


def listar_usuarios() -> QuerySet[Usuario]:
    """Usuarios con su persona y sus filas de rol, para mostrar el rol sin consultas extra."""
    return Usuario.objects.select_related('persona', 'admin', 'recepcionista', 'quimico').order_by(
        'persona__nombre', 'persona__apellido_paterno'
    )
