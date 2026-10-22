"""
Máquina de estados de EstudioPedido (CONTEXTO.md §5) y reglas de los derivados del pedido.

    pendiente ──asignar químico──▶ en_proceso ──completar──▶ completado ──enviar──▶ (fecha_envio)

Las reglas de los derivados son PROVISIONALES (CONTEXTO.md §8): están aisladas aquí.
"""

from collections.abc import Iterable
from decimal import Decimal

from django.core.exceptions import ValidationError

from apps.pedidos.models import EstadoEstudio, EstadoPago, EstadoPedido

TRANSICIONES = {
    EstadoEstudio.PENDIENTE: {EstadoEstudio.EN_PROCESO},
    EstadoEstudio.EN_PROCESO: {EstadoEstudio.COMPLETADO},
    EstadoEstudio.COMPLETADO: set(),
}


class TransicionInvalida(ValidationError):
    """Cambio de estado que la máquina no permite."""


def validar_transicion(actual: str, nuevo: str) -> None:
    if nuevo not in TRANSICIONES[actual]:
        raise TransicionInvalida(
            f'Un estudio {EstadoEstudio(actual).label.lower()} no puede pasar a '
            f'{EstadoEstudio(nuevo).label.lower()}.'
        )


def estado_del_pedido(estudios: Iterable) -> str:
    """
    Completado: todos completados y enviados (pagados o no). Pendiente: ninguno empezado.
    En proceso: cualquier otro caso.
    """
    estudios = list(estudios)
    if estudios and all(e.estado == EstadoEstudio.COMPLETADO and e.enviado for e in estudios):
        return EstadoPedido.COMPLETADO
    if all(e.estado == EstadoEstudio.PENDIENTE for e in estudios):
        return EstadoPedido.PENDIENTE
    return EstadoPedido.EN_PROCESO


def pago_del_pedido(estudios: Iterable) -> str:
    """PROVISIONAL. Pagado si todos lo están, pendiente si ninguno tiene pago, abonado si no."""
    pagos = {e.estado_pago for e in estudios}
    if pagos == {EstadoPago.PAGADO}:
        return EstadoPago.PAGADO
    if not pagos or pagos == {EstadoPago.PENDIENTE}:
        return EstadoPago.PENDIENTE
    return EstadoPago.ABONADO


def total_del_pedido(estudios: Iterable) -> Decimal:
    """PROVISIONAL. Lo que cuesta el pedido: la suma de los precios copiados."""
    return sum((e.precio for e in estudios), Decimal(0))
