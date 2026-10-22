from decimal import Decimal

from apps.estudios.definiciones.base import Campo, DefinicionEstudio, registrar


@registrar
class Glucosa(DefinicionEstudio):
    """PROVISIONAL. Sin cálculos: solo se captura el valor."""

    clave = 'GLU'
    campos = (Campo('glucosa', 'Glucosa en ayuno', unidad='mg/dL', decimales=0, minimo=Decimal(0)),)
