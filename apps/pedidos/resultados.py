"""
Resultados de un estudio listos para mostrarse (pantalla y, en la semana 8, el PDF).

Se leen del JSON guardado en `EstudioPedido.resultados`: los valores y la referencia que
se copió al completar. Si la referencia cambia después, lo entregado no cambia.
"""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

BAJO = 'bajo'
ALTO = 'alto'


@dataclass(frozen=True)
class Fila:
    clave: str
    etiqueta: str
    valor: str
    unidad: str = ''
    referencia: str = ''
    # 'bajo', 'alto' o '' (dentro del rango o sin rango numérico).
    marca: str = ''
    calculado: bool = False


def fuera_de_rango(valor, referencia: dict | None) -> str:
    """PROVISIONAL (CONTEXTO.md §8). Bajo si es menor al mínimo y alto si pasa del máximo."""
    if valor is None or not referencia:
        return ''
    try:
        numero = Decimal(str(valor))
    except InvalidOperation:
        return ''
    minimo, maximo = referencia.get('valor_minimo'), referencia.get('valor_maximo')
    if minimo is not None and numero < Decimal(minimo):
        return BAJO
    if maximo is not None and numero > Decimal(maximo):
        return ALTO
    return ''


def filas(estudio_pedido) -> list[Fila]:
    """Una fila por campo con valor guardado, en el orden de la definición."""
    datos = estudio_pedido.resultados or {}
    valores = datos.get('valores', {})
    referencias = datos.get('referencias', {})
    definicion = estudio_pedido.estudio.definicion
    campos = definicion.todos_los_campos() if definicion else ()
    calculados = {c.clave for c in definicion.calculados} if definicion else set()
    conocidos = {c.clave for c in campos}

    resultado = []
    for campo in campos:
        if campo.clave not in valores:
            continue
        referencia = referencias.get(campo.clave)
        valor = valores[campo.clave]
        resultado.append(
            Fila(
                clave=campo.clave,
                etiqueta=campo.etiqueta,
                valor='—' if valor is None else str(valor),
                unidad=(referencia or {}).get('unidad') or campo.unidad,
                referencia=(referencia or {}).get('rango', ''),
                marca=fuera_de_rango(valor, referencia),
                calculado=campo.clave in calculados,
            )
        )
    # Campos que ya no están en la definición (se capturaron con otra versión).
    for clave in valores.keys() - conocidos:
        valor = valores[clave]
        resultado.append(
            Fila(clave=clave, etiqueta=clave, valor='—' if valor is None else str(valor))
        )
    return resultado
