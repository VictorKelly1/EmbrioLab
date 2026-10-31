"""
Lo que hace el worker con un grupo de notificaciones creadas juntas (notificaciones/tasks.py).

- Link del formulario y recordatorio: se genera UN token para todo el grupo, así el
  correo y el WhatsApp llevan el mismo link. Al reintentar se genera otro y se manda a
  todos los canales del grupo: el link anterior ya no sirve (en la BD solo queda el hash).
- Resultados: un mensaje por canal con un solo PDF de todos los estudios del grupo.

Devuelve los ids que hay que reintentar; los errores definitivos (la cita se canceló,
el formulario ya se llenó) no se reintentan.
"""

import logging
from collections import defaultdict

from django.conf import settings
from django.core.exceptions import ValidationError
from django.urls import reverse

from apps.citas.models import EstadoCita
from apps.citas.services import generar_token_qr
from apps.documentos.pdf import pdf_resultados
from apps.notificaciones import mensajes
from apps.notificaciones.canales import canal
from apps.notificaciones.models import Notificacion, TipoNotificacion
from apps.notificaciones.services import marcar_enviada, marcar_fallida

logger = logging.getLogger(__name__)


def _enviar(notificacion: Notificacion, mensaje) -> bool:
    try:
        canal(notificacion.canal).enviar(mensaje)
    except Exception as error:  # cualquier falla del canal se registra
        logger.exception('Falló la notificación %s', notificacion.pk)
        marcar_fallida(notificacion, f'{type(error).__name__}: {error}')
        return False
    marcar_enviada(notificacion)
    return True


def _link(token: str) -> str:
    return settings.SITIO_URL + reverse('formulario_publico', args=[token])


def _procesar_cita(filas: list[Notificacion]) -> list[int]:
    tipo = filas[0].tipo
    cita = filas[0].cita
    if cita is None:
        for fila in filas:
            marcar_fallida(fila, 'La cita se canceló antes del envío.')
        return []
    if tipo == TipoNotificacion.RECORDATORIO and cita.estado != EstadoCita.PROGRAMADA:
        for fila in filas:
            marcar_fallida(fila, 'La cita ya no está programada.')
        return []
    try:
        link = _link(generar_token_qr(cita))
    except ValidationError as error:
        if tipo == TipoNotificacion.QR:
            for fila in filas:
                marcar_fallida(fila, ' '.join(error.messages))
            return []
        link = None  # el recordatorio sale sin link si ya llenó el formulario
    if tipo == TipoNotificacion.RECORDATORIO:
        armar = mensajes.recordatorio
    else:
        armar = mensajes.link_formulario
    enviados = [_enviar(fila, armar(fila.destinatario, cita, link)) for fila in filas]
    if all(enviados):
        return []
    # Con un link nuevo, todos los canales deben recibirlo.
    if link:
        return [f.pk for f in filas]
    return [f.pk for f, ok in zip(filas, enviados, strict=True) if not ok]


def _procesar_resultados(filas: list[Notificacion]) -> list[int]:
    por_destino = defaultdict(list)
    for fila in filas:
        if fila.estudio_pedido is None:
            marcar_fallida(fila, 'El estudio ya no existe.')
        else:
            por_destino[fila.canal, fila.destinatario].append(fila)
    pdfs = {}
    fallidas = []
    for grupo in por_destino.values():
        estudios = [f.estudio_pedido for f in grupo]
        clave = tuple(e.pk for e in estudios)
        try:
            if clave not in pdfs:
                pdfs[clave] = pdf_resultados(estudios)
        except Exception as error:
            logger.exception('No se pudo generar el PDF de %s', clave)
            for fila in grupo:
                marcar_fallida(fila, f'No se pudo generar el PDF. {type(error).__name__}: {error}')
            fallidas += [f.pk for f in grupo]
            continue
        mensaje = mensajes.resultados(grupo[0].destinatario, estudios, pdfs[clave])
        # Un solo mensaje por canal y destinatario; cuenta para todas sus filas.
        if _enviar(grupo[0], mensaje):
            for fila in grupo[1:]:
                marcar_enviada(fila)
        else:
            for fila in grupo[1:]:
                marcar_fallida(fila, grupo[0].error)
            fallidas += [f.pk for f in grupo]
    return fallidas


def procesar(ids: list[int]) -> list[int]:
    filas = list(
        Notificacion.objects.filter(pk__in=ids)
        .select_related(
            'cita__paciente__persona',
            'estudio_pedido__estudio__categoria',
            'estudio_pedido__pedido__cita__paciente__persona',
            'estudio_pedido__pedido__doctor',
            'estudio_pedido__quimico_completo__usuario__persona',
        )
        .order_by('estudio_pedido_id', 'id')
    )
    if not filas:
        return []
    if filas[0].tipo == TipoNotificacion.RESULTADOS:
        return _procesar_resultados(filas)
    return _procesar_cita(filas)
