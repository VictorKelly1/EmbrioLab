from django.db.models import QuerySet

from apps.notificaciones.models import Notificacion


def notificaciones_de_cita(cita) -> QuerySet[Notificacion]:
    return Notificacion.objects.filter(cita=cita)


def notificaciones_de_pedido(pedido) -> QuerySet[Notificacion]:
    """Los envíos de resultados del pedido, con el estudio de cada uno."""
    return Notificacion.objects.filter(estudio_pedido__pedido=pedido).select_related(
        'estudio_pedido__estudio'
    )
