import datetime

from django.db.models import Count, Exists, OuterRef, Prefetch, Q, QuerySet

from apps.citas.models import Cita
from apps.core.texto import normalizar
from apps.cuentas.models import Quimico
from apps.pacientes.models import Paciente
from apps.pedidos.models import AsignacionQuimico, EstadoEstudio, EstudioPedido, Pedido


def _con_paciente(pedidos: QuerySet[Pedido]) -> QuerySet[Pedido]:
    return pedidos.select_related('cita__paciente__persona', 'doctor').annotate(
        num_estudios=Count('estudios')
    )


def buscar_pedidos(
    termino: str = '',
    *,
    estado: str = '',
    estado_pago: str = '',
    quimico: Quimico | None = None,
    desde: datetime.date | None = None,
    hasta: datetime.date | None = None,
) -> QuerySet[Pedido]:
    """
    Por número de pedido, folio o nombre del paciente; con filtros de estado, pago,
    químico asignado (a cualquiera de sus estudios) y fecha del pedido (ambas incluidas).
    """
    pedidos = _con_paciente(Pedido.objects.order_by('-fecha_inicio', '-id'))
    if estado:
        pedidos = pedidos.filter(estado=estado)
    if estado_pago:
        pedidos = pedidos.filter(estado_pago=estado_pago)
    if quimico:
        # Exists y no un join: el join duplicaría filas y el conteo de estudios.
        pedidos = pedidos.filter(
            Exists(
                AsignacionQuimico.objects.filter(
                    estudio_pedido__pedido=OuterRef('pk'), quimico=quimico
                )
            )
        )
    if desde:
        pedidos = pedidos.filter(fecha_inicio__date__gte=desde)
    if hasta:
        pedidos = pedidos.filter(fecha_inicio__date__lte=hasta)
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
                queryset=EstudioPedido.objects.select_related('estudio').prefetch_related(
                    'quimicos_asignados__usuario__persona'
                ),
            )
        )
        .get(pk=pk)
    )


def estudios_completados(pedido: Pedido, ids=None) -> QuerySet[EstudioPedido]:
    """Los que ya tienen resultados para entregar (PDF y envío); con `ids`, solo esos."""
    estudios = EstudioPedido.objects.filter(
        pedido=pedido, estado=EstadoEstudio.COMPLETADO
    ).select_related(
        'estudio__categoria',
        'pedido__cita__paciente__persona',
        'pedido__doctor',
        'quimico_completo__usuario__persona',
    )
    if ids is not None:
        estudios = estudios.filter(pk__in=ids)
    return estudios.order_by('id')


def _estudios_con_pedido() -> QuerySet[EstudioPedido]:
    return EstudioPedido.objects.select_related('estudio', 'pedido__cita__paciente__persona')


def lista_de_trabajo(quimico: Quimico) -> QuerySet[EstudioPedido]:
    """Estudios en proceso donde el químico es uno de los responsables; los más viejos primero."""
    return (
        _estudios_con_pedido()
        .filter(estado=EstadoEstudio.EN_PROCESO, asignaciones__quimico=quimico)
        .order_by('pedido__fecha_inicio', 'id')
    )


def obtener_estudio_pedido(pk: int) -> EstudioPedido:
    return (
        _estudios_con_pedido()
        .select_related('quimico_completo__usuario__persona')
        .prefetch_related('quimicos_asignados__usuario__persona')
        .get(pk=pk)
    )


def historial_de_paciente(
    paciente: Paciente, *, estudio=None, excluir: EstudioPedido | None = None
) -> QuerySet[EstudioPedido]:
    """
    Estudios del paciente en todos sus pedidos, los más recientes primero. Con `estudio`,
    solo los completados de ese estudio: para comparar con resultados anteriores.
    """
    estudios = _estudios_con_pedido().filter(pedido__cita__paciente=paciente)
    if estudio is not None:
        estudios = estudios.filter(estudio=estudio, estado=EstadoEstudio.COMPLETADO)
    if excluir is not None:
        estudios = estudios.exclude(pk=excluir.pk)
    return estudios.order_by('-pedido__fecha_inicio', '-id')


def quimicos_activos() -> QuerySet[Quimico]:
    return (
        Quimico.objects.filter(estado_actividad=True, usuario__is_active=True)
        .select_related('usuario__persona')
        .order_by('usuario__persona__nombre', 'usuario__persona__apellido_paterno')
    )
