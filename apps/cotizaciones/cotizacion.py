"""
Cotización de un conjunto de estudios (un «paquete» temporal). NO se guarda en la BD
(CONTEXTO.md §3): se calcula con los precios vigentes del catálogo cada vez que se pide.
"""

import datetime
from dataclasses import dataclass
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.utils import timezone


@dataclass(frozen=True)
class Renglon:
    clave: str
    nombre: str
    categoria: str
    precio: Decimal


@dataclass(frozen=True)
class Cotizacion:
    cliente: str
    renglones: tuple[Renglon, ...]
    fecha: datetime.date

    @property
    def total(self) -> Decimal:
        return sum((r.precio for r in self.renglones), Decimal(0))


def cotizar(estudios, *, cliente: str = '', fecha: datetime.date | None = None) -> Cotizacion:
    """
    Los estudios elegidos, en el orden recibido, con su precio vigente y el total.
    PROVISIONAL (CONTEXTO.md §8): sin descuentos ni vigencia.
    """
    estudios = list(estudios)
    if not estudios:
        raise ValidationError('Elija al menos un estudio para cotizar.')
    if len({e.pk for e in estudios}) != len(estudios):
        raise ValidationError('Hay un estudio repetido en la cotización.')
    inactivos = [e.nombre for e in estudios if not e.activo]
    if inactivos:
        raise ValidationError(f'Ya no están activos en el catálogo: {", ".join(inactivos)}.')
    return Cotizacion(
        cliente=' '.join(cliente.split()),
        renglones=tuple(Renglon(e.clave, e.nombre, str(e.categoria), e.precio) for e in estudios),
        fecha=fecha or timezone.localdate(),
    )
