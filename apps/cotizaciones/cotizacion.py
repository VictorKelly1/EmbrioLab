"""
Cotización de un conjunto de estudios (un «paquete» temporal). NO se guarda en la BD
(CONTEXTO.md §3): se calcula con los precios vigentes del catálogo cada vez que se pide.
También admite estudios «libres» que no están en el catálogo, con el nombre y el precio
que escribe la recepción.
"""

import datetime
from dataclasses import dataclass
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.utils import timezone

CATEGORIA_LIBRE = 'Otros'


@dataclass(frozen=True)
class Renglon:
    clave: str  # vacía en un estudio libre
    nombre: str
    categoria: str
    precio: Decimal


@dataclass(frozen=True)
class EstudioLibre:
    """Un estudio que no está en el catálogo. La categoría es opcional."""

    nombre: str
    precio: Decimal
    categoria: str = ''


@dataclass(frozen=True)
class Cotizacion:
    cliente: str
    renglones: tuple[Renglon, ...]
    fecha: datetime.date

    @property
    def total(self) -> Decimal:
        return sum((r.precio for r in self.renglones), Decimal(0))


def cotizar(
    estudios=(),
    *,
    libres=(),
    cliente: str = '',
    fecha: datetime.date | None = None,
) -> Cotizacion:
    """
    Los estudios del catálogo, en el orden recibido, con su precio vigente; después los
    libres, en su orden; y el total. PROVISIONAL (CONTEXTO.md §8): sin descuentos ni vigencia.
    """
    estudios = list(estudios)
    libres = [_limpiar(libre) for libre in libres]
    if not estudios and not libres:
        raise ValidationError('Elija al menos un estudio para cotizar.')
    if len({e.pk for e in estudios}) != len(estudios):
        raise ValidationError('Hay un estudio repetido en la cotización.')
    inactivos = [e.nombre for e in estudios if not e.activo]
    if inactivos:
        raise ValidationError(f'Ya no están activos en el catálogo: {", ".join(inactivos)}.')
    renglones = [Renglon(e.clave, e.nombre, str(e.categoria), e.precio) for e in estudios]
    renglones += [Renglon('', libre.nombre, libre.categoria, libre.precio) for libre in libres]
    return Cotizacion(
        cliente=' '.join(cliente.split()),
        renglones=tuple(renglones),
        fecha=fecha or timezone.localdate(),
    )


def _limpiar(libre: EstudioLibre) -> EstudioLibre:
    nombre = ' '.join(libre.nombre.split())
    if not nombre:
        raise ValidationError('Escriba el nombre de cada estudio que no está en el catálogo.')
    if libre.precio is None or libre.precio < 0:
        raise ValidationError(f'Escriba un precio válido para «{nombre}».')
    categoria = ' '.join(libre.categoria.split()) or CATEGORIA_LIBRE
    return EstudioLibre(nombre, libre.precio, categoria)
