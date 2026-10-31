"""
Un adapter por canal con la misma interfaz (CONTEXTO.md §5). El worker no sabe cómo
sale cada mensaje: pide el canal y llama a `enviar`. Si falla, el canal lanza la excepción.
"""

import logging
from dataclasses import dataclass, field

from django.conf import settings
from django.core.mail import EmailMessage

from apps.notificaciones.models import Canal

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Adjunto:
    nombre: str
    contenido: bytes
    tipo_mime: str


@dataclass(frozen=True)
class Mensaje:
    destinatario: str
    asunto: str
    texto: str
    adjuntos: tuple[Adjunto, ...] = field(default=())


class CanalCorreo:
    """SMTP en producción; en desarrollo el backend de consola (settings MAILERS)."""

    def enviar(self, mensaje: Mensaje) -> None:
        correo = EmailMessage(
            subject=mensaje.asunto,
            body=mensaje.texto,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[mensaje.destinatario],
        )
        for adjunto in mensaje.adjuntos:
            correo.attach(adjunto.nombre, adjunto.contenido, adjunto.tipo_mime)
        correo.send()


class CanalWhatsApp:
    """
    STUB hasta integrar la API de WhatsApp (fuera de la Fase 1): solo deja constancia en
    el log y cuenta como enviado. La integración real va aquí, con la misma interfaz.
    """

    def enviar(self, mensaje: Mensaje) -> None:
        logger.info(
            'WhatsApp (sin integrar) a %s: %s [%d adjunto(s)]',
            mensaje.destinatario,
            mensaje.asunto,
            len(mensaje.adjuntos),
        )


CANALES = {
    Canal.CORREO: CanalCorreo(),
    Canal.WHATSAPP: CanalWhatsApp(),
}


def canal(nombre: str):
    return CANALES[nombre]
