from django.db.models import Count, Prefetch, Q, QuerySet

from apps.citas.models import Cita
from apps.core.texto import normalizar
from apps.cuentas.models import Quimico
from apps.pedidos.models import EstudioPedido, Pedido


def _con_paciente(pedidos: QuerySet[Pedido]) -> QuerySet[Pedido]:
    return pedidos.select_related('cita__paciente__persona', 'doctor').annotate(
        num_estudios=Count('estudios')
    )


def buscar_pedidos(
    termino: str = '', *, estado: str = '', estado_pago: str = ''
) -> QuerySet[Pedido]:
    """Por número de pedido, folio o nombre del paciente; con filtros de estado y pago."""
    pedidos = _con_paciente(Pedido.objects.order_by('-fecha_inicio', '-id'))
    if estado:
        pedidos = pedidos.filter(estado=estado)
    if estado_pago:
        pedidos = pedidos.filter(estado_pago=estado_pago)
    termino = termino.strip()
    if termino:
        pedidos = pedidos.filter(
            Q(numero__icontains=termino)
            | Q(cita__numero_folio__iexact=termino)
            | Q(cita__paciente__persona__nombre_busqueda__contains=normalizar(termino))
        )
    return pedidos


def pedidos_de_cita(cita: Cita) -> QuerySet[Pedido]:
    return _con_paciente(cita.pedidos.all()).order_by('fecha_inicio')


def obtener_pedido(pk: int) -> Pedido:
    return (
        Pedido.objects.select_related(
            'cita__paciente__persona', 'doctor', 'recepcionista__usuario__persona'
        )
        .prefetch_related(
            Prefetch(
                'estudios',
                queryset=EstudioPedido.objects.select_related(
                    'estudio', 'quimico_asignado__usuario__persona'
                ),
            )
        )
        .get(pk=pk)
    )


def quimicos_activos() -> QuerySet[Quimico]:
    return (
        Quimico.objects.filter(estado_actividad=True, usuario__is_active=True)
        .select_related('usuario__persona')
        .order_by('usuario__persona__nombre', 'usuario__persona__apellido_paterno')
    )
