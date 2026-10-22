"""
Número de pedido. PROVISIONAL (CONTEXTO.md §8): año + consecutivo, `2026-0001`.
El cliente define el formato; si cambia, solo se toca este archivo.
"""

from django.db import connection
from django.utils import timezone

from apps.pedidos.models import ConsecutivoPedido


def siguiente_numero(fecha=None) -> str:
    """
    Toma el siguiente consecutivo del año en un solo `INSERT … ON CONFLICT`, así dos
    pedidos simultáneos nunca reciben el mismo. Si la transacción se revierte, el número
    también: no quedan huecos.
    """
    anio = (fecha or timezone.localdate()).year
    tabla = ConsecutivoPedido._meta.db_table
    with connection.cursor() as cursor:
        cursor.execute(
            f'INSERT INTO {tabla} (anio, ultimo) VALUES (%s, 1) '
            f'ON CONFLICT (anio) DO UPDATE SET ultimo = {tabla}.ultimo + 1 '
            'RETURNING ultimo',
            [anio],
        )
        consecutivo = cursor.fetchone()[0]
    return formatear(anio, consecutivo)


def formatear(anio: int, consecutivo: int) -> str:
    return f'{anio}-{consecutivo:04d}'
