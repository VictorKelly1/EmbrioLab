from decimal import Decimal

from apps.estudios.definiciones.base import Campo, DefinicionEstudio, registrar

# Con triglicéridos de 400 mg/dL o más, la fórmula de Friedewald no es confiable.
TRIGLICERIDOS_MAXIMO_FRIEDEWALD = Decimal(400)


@registrar
class PerfilLipidos(DefinicionEstudio):
    """PROVISIONAL. LDL por Friedewald e índice aterogénico (Castelli)."""

    clave = 'PLIP'
    campos = (
        Campo(
            'colesterol_total', 'Colesterol total', unidad='mg/dL', decimales=0, minimo=Decimal(0)
        ),
        Campo('hdl', 'Colesterol HDL', unidad='mg/dL', decimales=0, minimo=Decimal(0)),
        Campo('trigliceridos', 'Triglicéridos', unidad='mg/dL', decimales=0, minimo=Decimal(0)),
    )
    calculados = (
        Campo(
            'ldl',
            'Colesterol LDL',
            unidad='mg/dL',
            decimales=0,
            formula='Colesterol total − HDL − Triglicéridos ÷ 5 (si triglicéridos < 400)',
        ),
        Campo(
            'indice_aterogenico',
            'Índice aterogénico',
            decimales=1,
            formula='Colesterol total ÷ HDL',
        ),
    )

    def calcular(self, valores, paciente):
        total = valores['colesterol_total']
        hdl = valores['hdl']
        trigliceridos = valores['trigliceridos']
        ldl = None
        if trigliceridos < TRIGLICERIDOS_MAXIMO_FRIEDEWALD:
            ldl = total - hdl - trigliceridos / 5
        return {
            'ldl': ldl,
            'indice_aterogenico': total / hdl if hdl else None,
        }
