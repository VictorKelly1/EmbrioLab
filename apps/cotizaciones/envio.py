"""
Envío de una cotización. Decidido con el cliente (2026-11-03): sale directo, sin pasar
por la tabla Notificaciones ni el worker, porque la cotización no se guarda. Por eso no
hay reintentos: si un canal falla, la recepción ve el error y puede volver a enviarla.
"""

import logging

from django.core.exceptions import ValidationError

from apps.documentos.pdf import pdf_cotizacion
from apps.notificaciones import mensajes
from apps.notificaciones.canales import canal
from apps.notificaciones.models import Canal
from apps.notificaciones.services import destinatarios

logger = logging.getLogger(__name__)


def destinos_para(*, paciente=None, correo: str = '', whatsapp: str = '') -> dict[str, str]:
    """
    {canal: destinatario}. Los contactos principales del paciente registrado, si hay uno;
    lo escrito en las cajas reemplaza al contacto de ese canal (o es el único destino).
    """
    destinos = destinatarios(paciente.persona) if paciente is not None else {}
    if correo.strip():
        destinos[Canal.CORREO] = correo.strip()
    if whatsapp.strip():
        destinos[Canal.WHATSAPP] = whatsapp.strip()
    return destinos


def enviar_cotizacion(cotizacion, destinos: dict[str, str]) -> dict[str, str]:
    """
    Manda la cotización con su PDF por cada canal. Regresa {canal: error} de los que
    fallaron (vacío si todos salieron).
    """
    if not destinos:
        raise ValidationError('Elija un paciente con correo o WhatsApp, o escriba un correo.')
    pdf = pdf_cotizacion(cotizacion)
    fallidos = {}
    for nombre, destinatario in destinos.items():
        try:
            canal(nombre).enviar(mensajes.cotizacion(destinatario, cotizacion, pdf))
        except Exception as error:  # cualquier falla del canal se reporta, no rompe la página
            logger.exception('No se pudo enviar la cotización por %s', nombre)
            fallidos[nombre] = str(error) or error.__class__.__name__
    return fallidos
