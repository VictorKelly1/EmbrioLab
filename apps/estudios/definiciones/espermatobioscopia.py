from decimal import Decimal

from django.core.exceptions import ValidationError

from apps.estudios.definiciones.base import Campo, DefinicionEstudio, registrar

PORCENTAJE = {'unidad': '%', 'decimales': 0, 'minimo': Decimal(0), 'maximo': Decimal(100)}
MOVILIDAD = ('movilidad_progresiva', 'movilidad_no_progresiva', 'inmoviles')


@registrar
class Espermatobioscopia(DefinicionEstudio):
    """PROVISIONAL. Versión básica: volumen, concentración y movilidad."""

    clave = 'ESP'
    campos = (
        Campo('volumen', 'Volumen', unidad='mL', decimales=1, minimo=Decimal(0)),
        Campo(
            'concentracion', 'Concentración', unidad='millones/mL', decimales=1, minimo=Decimal(0)
        ),
        Campo('movilidad_progresiva', 'Movilidad progresiva', **PORCENTAJE),
        Campo('movilidad_no_progresiva', 'Movilidad no progresiva', **PORCENTAJE),
        Campo('inmoviles', 'Inmóviles', **PORCENTAJE),
        Campo('aspecto', 'Aspecto', tipo='opcion', opciones=('Normal', 'Anormal')),
    )
    calculados = (
        Campo(
            'total_espermatozoides',
            'Número total de espermatozoides',
            unidad='millones',
            decimales=1,
            formula='Volumen × Concentración',
        ),
        Campo(
            'total_moviles_progresivos',
            'Total de móviles progresivos',
            unidad='millones',
            decimales=1,
            formula='Número total × Movilidad progresiva ÷ 100',
        ),
    )

    def validar(self, valores):
        if sum(valores[clave] for clave in MOVILIDAD) != 100:
            raise ValidationError(
                'La movilidad progresiva, no progresiva e inmóviles deben sumar 100 %.'
            )

    def calcular(self, valores, paciente):
        total = valores['volumen'] * valores['concentracion']
        return {
            'total_espermatozoides': total,
            'total_moviles_progresivos': total * valores['movilidad_progresiva'] / 100,
        }
