"""
Límite de peticiones propio, sin dependencias externas.

Ventana fija por clave guardada en PostgreSQL: funciona igual con varios workers de
gunicorn. El incremento es un solo INSERT … ON CONFLICT, atómico aunque lleguen
peticiones simultáneas.
"""

import datetime

from django.conf import settings
from django.db import connection
from django.utils import timezone

from apps.core.models import ContadorIntentos

_SQL = f"""
INSERT INTO {ContadorIntentos._meta.db_table} (clave, inicio_ventana, conteo)
VALUES (%(clave)s, %(ahora)s, 1)
ON CONFLICT (clave) DO UPDATE SET
    conteo = CASE
        WHEN {ContadorIntentos._meta.db_table}.inicio_ventana <= %(limite)s THEN 1
        ELSE {ContadorIntentos._meta.db_table}.conteo + 1
    END,
    inicio_ventana = CASE
        WHEN {ContadorIntentos._meta.db_table}.inicio_ventana <= %(limite)s THEN %(ahora)s
        ELSE {ContadorIntentos._meta.db_table}.inicio_ventana
    END
RETURNING conteo
"""


def registrar_intento(clave: str, *, maximo: int, ventana: datetime.timedelta) -> bool:
    """Cuenta un intento. Devuelve True si la clave ya pasó de `maximo` en la ventana."""
    ahora = timezone.now()
    with connection.cursor() as cursor:
        cursor.execute(_SQL, {'clave': clave[:200], 'ahora': ahora, 'limite': ahora - ventana})
        (conteo,) = cursor.fetchone()
    return conteo > maximo


def agotado(clave: str, *, maximo: int, ventana: datetime.timedelta) -> bool:
    """True si la clave ya usó sus `maximo` intentos en la ventana. No cuenta uno nuevo."""
    return ContadorIntentos.objects.filter(
        clave=clave[:200], inicio_ventana__gt=timezone.now() - ventana, conteo__gte=maximo
    ).exists()


def limpiar_vencidos(antiguedad: datetime.timedelta = datetime.timedelta(days=1)) -> int:
    borrados, _ = ContadorIntentos.objects.filter(
        inicio_ventana__lt=timezone.now() - antiguedad
    ).delete()
    return borrados


def ip_cliente(request) -> str:
    """
    IP del cliente. Detrás de nginx (producción) se toma la última dirección de
    X-Forwarded-For, que es la que agregó nginx; el resto la puede inventar el cliente.
    """
    if getattr(settings, 'IP_DESDE_PROXY', False):
        reenviada = request.META.get('HTTP_X_FORWARDED_FOR', '')
        if reenviada:
            return reenviada.split(',')[-1].strip()
    return request.META.get('REMOTE_ADDR', '')
