"""
Registro + Strategy de los estudios (CONTEXTO.md §5).

Cada estudio es una subclase de `DefinicionEstudio` registrada con `@registrar`. Su `clave`
enlaza con la fila `Estudio` de la BD; el system check `estudios.E00x` avisa si no coinciden.

    @registrar
    class Glucosa(DefinicionEstudio):
        clave = 'GLU'
        campos = (Campo('glucosa', 'Glucosa', unidad='mg/dL'),)

`campos` son los que captura el químico; `calculados` los obtiene `calcular()`.
Si cambian los campos o las fórmulas, sube `version` (y `Estudio.version_definicion` con
una migración de datos): cada EstudioPedido guarda la versión con la que se capturó.
"""

from dataclasses import dataclass
from decimal import Decimal

from django.core.exceptions import ImproperlyConfigured

TIPOS_CAMPO = ('decimal', 'entero', 'texto', 'opcion')


@dataclass(frozen=True)
class Campo:
    clave: str
    etiqueta: str
    tipo: str = 'decimal'
    unidad: str = ''
    decimales: int = 2
    minimo: Decimal | None = None
    maximo: Decimal | None = None
    opciones: tuple[str, ...] = ()
    # Solo en los calculados: cómo se obtiene, para mostrarlo en el catálogo.
    formula: str = ''


class DefinicionEstudio:
    clave: str = ''
    version: int = 1
    campos: tuple[Campo, ...] = ()
    calculados: tuple[Campo, ...] = ()

    def validar(self, valores: dict) -> None:
        """Reglas entre campos. Lanza ValidationError si los valores no tienen sentido juntos."""

    def calcular(self, valores: dict, paciente) -> dict:
        """Valores de `calculados` a partir de los capturados. None = no se puede calcular."""
        return {}

    def resultados(self, valores: dict, paciente) -> dict:
        """Valida, calcula y redondea: lo que se guarda en `EstudioPedido.resultados`."""
        self.validar(valores)
        calculados = self.calcular(valores, paciente)
        return {
            **valores,
            **{c.clave: _redondear(calculados.get(c.clave), c) for c in self.calculados},
        }

    @classmethod
    def todos_los_campos(cls) -> tuple[Campo, ...]:
        return cls.campos + cls.calculados

    @classmethod
    def campo(cls, clave: str) -> Campo | None:
        return next((c for c in cls.todos_los_campos() if c.clave == clave), None)


def _redondear(valor, campo: Campo):
    if valor is None or campo.tipo not in ('decimal', 'entero'):
        return valor
    return Decimal(valor).quantize(Decimal(1).scaleb(-campo.decimales))


REGISTRO: dict[str, type[DefinicionEstudio]] = {}


def registrar(definicion: type[DefinicionEstudio]) -> type[DefinicionEstudio]:
    _revisar(definicion)
    if definicion.clave in REGISTRO:
        raise ImproperlyConfigured(f'Ya hay una definición con la clave {definicion.clave!r}.')
    REGISTRO[definicion.clave] = definicion
    return definicion


def _revisar(definicion: type[DefinicionEstudio]) -> None:
    nombre = definicion.__name__
    if not definicion.clave:
        raise ImproperlyConfigured(f'{nombre} no tiene `clave`.')
    if not definicion.campos:
        raise ImproperlyConfigured(f'{nombre} no tiene `campos`.')
    claves = [c.clave for c in definicion.todos_los_campos()]
    repetidas = {c for c in claves if claves.count(c) > 1}
    if repetidas:
        raise ImproperlyConfigured(f'{nombre} repite campos: {", ".join(sorted(repetidas))}.')
    for campo in definicion.todos_los_campos():
        if campo.tipo not in TIPOS_CAMPO:
            raise ImproperlyConfigured(f'{nombre}.{campo.clave}: tipo {campo.tipo!r} no válido.')
        if campo.tipo == 'opcion' and not campo.opciones:
            raise ImproperlyConfigured(f'{nombre}.{campo.clave}: falta `opciones`.')


def obtener(clave: str) -> DefinicionEstudio | None:
    definicion = REGISTRO.get(clave)
    return definicion() if definicion else None
