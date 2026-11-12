import datetime
from dataclasses import dataclass

from django.db.models import Count, Exists, OuterRef, Prefetch, Q, QuerySet

from apps.citas.models import Cita, EstadoCita
from apps.core.texto import normalizar
from apps.cuentas.models import Quimico
from apps.pacientes.models import Paciente
from apps.pedidos.models import EstadoEstudio, EstudioPedido, ObservacionPedido, Pedido


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
    químico encargado (de cualquiera de sus estudios) y fecha del pedido (ambas incluidas).
    """
    pedidos = _con_paciente(Pedido.objects.order_by('-fecha_inicio', '-id'))
    if estado:
        pedidos = pedidos.filter(estado=estado)
    if estado_pago:
        pedidos = pedidos.filter(estado_pago=estado_pago)
    if quimico:
        # Exists y no un join: el join duplicaría filas y el conteo de estudios.
        pedidos = pedidos.filter(
            Exists(EstudioPedido.objects.filter(pedido=OuterRef('pk'), quimico_encargado=quimico))
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
                queryset=EstudioPedido.objects.select_related(
                    'estudio', 'quimico_encargado__usuario__persona'
                ),
            ),
            Prefetch(
                'observaciones',
                queryset=ObservacionPedido.objects.select_related('usuario__persona'),
            ),
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
    """Estudios en proceso a cargo del químico; los más viejos primero."""
    return (
        _estudios_con_pedido()
        .filter(estado=EstadoEstudio.EN_PROCESO, quimico_encargado=quimico)
        .order_by('pedido__fecha_inicio', 'id')
    )


def cola_de_estudios() -> QuerySet[EstudioPedido]:
    """
    Estudios sin encargado que esperan a que un químico los tome, de citas atendidas
    (CONTEXTO.md §3). Ordenados por pedido, los más viejos primero, para agruparlos.
    """
    return (
        _estudios_con_pedido()
        .select_related('pedido__doctor')
        .filter(
            estado=EstadoEstudio.PENDIENTE,
            quimico_encargado__isnull=True,
            pedido__cita__estado=EstadoCita.ATENDIDA,
        )
        .order_by('pedido__fecha_inicio', 'pedido_id', 'id')
    )


@dataclass(frozen=True)
class PacienteEnCola:
    """Un paciente de la cola con sus estudios en espera, de todos sus pedidos."""

    paciente: Paciente
    estudios: list[EstudioPedido]

    @property
    def desde(self) -> datetime.datetime:
        return self.estudios[0].pedido.fecha_inicio

    @property
    def pedidos(self) -> list[Pedido]:
        vistos = {}
        for estudio in self.estudios:
            vistos.setdefault(estudio.pedido_id, estudio.pedido)
        return list(vistos.values())


def cola_por_paciente() -> list[PacienteEnCola]:
    """
    La cola agrupada por paciente (CONTEXTO.md §3): el químico toma al paciente con
    todos sus estudios en espera. Primero el que lleva más tiempo esperando.
    """
    grupos: dict[int, list[EstudioPedido]] = {}
    for estudio in cola_de_estudios():
        grupos.setdefault(estudio.pedido.cita.paciente_id, []).append(estudio)
    return [PacienteEnCola(e[0].pedido.cita.paciente, e) for e in grupos.values()]


def estudios_del_paciente(paciente: Paciente) -> QuerySet[EstudioPedido]:
    return EstudioPedido.objects.filter(pedido__cita__paciente=paciente)


def encargado_del_paciente(paciente: Paciente) -> Quimico | None:
    """
    El químico a cargo del paciente: el de sus estudios en proceso (todos tienen el
    mismo, CONTEXTO.md §3). Sin estudios en proceso, el paciente no tiene encargado.
    """
    estudio = (
        estudios_del_paciente(paciente)
        .filter(estado=EstadoEstudio.EN_PROCESO)
        .select_related('quimico_encargado__usuario__persona')
        .first()
    )
    return estudio.quimico_encargado if estudio else None


@dataclass(frozen=True)
class TomaDelPaciente:
    """Para las pantallas: quién tiene al paciente y qué puede hacer el químico que mira."""

    encargado: Quimico | None
    en_espera: int
    puede_tomar: bool
    puede_soltar: bool


def toma_del_paciente(paciente: Paciente, quimico: Quimico | None) -> TomaDelPaciente:
    """Los servicios vuelven a revisar todo; esto solo decide qué botones mostrar."""
    encargado = encargado_del_paciente(paciente)
    en_espera = cola_de_estudios().filter(pedido__cita__paciente=paciente).count()
    propio = quimico is not None and encargado is not None and encargado.pk == quimico.pk
    puede_soltar = False
    if propio:
        a_cargo = estudios_del_paciente(paciente).filter(
            estado=EstadoEstudio.EN_PROCESO, quimico_encargado=quimico
        )
        # Un borrador vacío no cuenta como captura (services.tiene_captura).
        puede_soltar = not any((e.resultados or {}).get('valores') for e in a_cargo)
    return TomaDelPaciente(
        encargado=encargado,
        en_espera=en_espera,
        puede_tomar=quimico is not None and en_espera > 0 and (encargado is None or propio),
        puede_soltar=puede_soltar,
    )


def obtener_estudio_pedido(pk: int) -> EstudioPedido:
    return (
        _estudios_con_pedido()
        .select_related('quimico_completo__usuario__persona', 'quimico_encargado__usuario__persona')
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
