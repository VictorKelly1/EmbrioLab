"""
Outbox de notificaciones (CONTEXTO.md §5):
  1. El servicio crea las filas `pendiente` en la misma transacción que el cambio.
  2. `transaction.on_commit` encola la tarea; si la transacción se revierte, no sale nada.
  3. El worker envía, marca `enviado` o `fallido` y reintenta (notificaciones/envio.py).
"""

import datetime
from functools import partial

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.citas.models import Cita, EstadoCita
from apps.citas.services import marcar_recordatorio_enviado, tiene_formulario_llenado
from apps.notificaciones.models import (
    Canal,
    EstadoNotificacion,
    Notificacion,
    TipoNotificacion,
)
from apps.personas.selectors import contactos_principales

# Qué contacto principal de la persona usa cada canal.
CONTACTO_DE_CANAL = {
    Canal.CORREO: 'correo',
    Canal.WHATSAPP: 'whatsapp',
}


def destinatarios(persona) -> dict[str, str]:
    """{canal: destinatario} con los contactos principales que tiene la persona."""
    contactos = contactos_principales(persona)
    return {
        canal: contactos[contacto]
        for canal, contacto in CONTACTO_DE_CANAL.items()
        if contactos.get(contacto)
    }


def _destinatarios_o_error(persona) -> dict[str, str]:
    destinos = destinatarios(persona)
    if not destinos:
        raise ValidationError(
            'El paciente no tiene correo ni WhatsApp registrado. Agréguelo en su ficha.'
        )
    return destinos


def _encolar(ids: list[int]) -> None:
    from apps.notificaciones.tasks import encolar

    encolar(ids)


def _crear(tipo: str, destinos: dict[str, str], *, cita=None, estudios=()) -> list[Notificacion]:
    """Una fila por canal (y por estudio, en resultados). Se encolan juntas al confirmar."""
    filas = [
        Notificacion(
            tipo=tipo, canal=canal, destinatario=destino, cita=cita, estudio_pedido=estudio
        )
        for canal, destino in destinos.items()
        for estudio in (estudios or [None])
    ]
    Notificacion.objects.bulk_create(filas)
    transaction.on_commit(partial(_encolar, [f.pk for f in filas]))
    return filas


@transaction.atomic
def enviar_link_formulario(cita: Cita) -> list[Notificacion]:
    """
    Manda al paciente el link del formulario de la cita. El token se genera al enviar
    (en la BD solo queda su hash) e invalida cualquier link anterior de la cita.
    """
    if cita.estado == EstadoCita.NO_ATENDIDA:
        raise ValidationError('La cita no fue atendida.')
    if tiene_formulario_llenado(cita):
        raise ValidationError('El paciente ya llenó el formulario de esta cita.')
    destinos = _destinatarios_o_error(cita.paciente.persona)
    return _crear(TipoNotificacion.QR, destinos, cita=cita)


@transaction.atomic
def enviar_recordatorio(cita: Cita) -> list[Notificacion]:
    """
    Recordatorio de la cita con el link del formulario. Si el paciente no tiene a dónde
    enviarlo, no hace nada y la cita sigue sin recordatorio.
    """
    cita = Cita.objects.select_for_update().select_related('paciente__persona').get(pk=cita.pk)
    if cita.recordatorio_enviado or cita.estado != EstadoCita.PROGRAMADA:
        return []
    destinos = destinatarios(cita.paciente.persona)
    if not destinos:
        return []
    filas = _crear(TipoNotificacion.RECORDATORIO, destinos, cita=cita)
    marcar_recordatorio_enviado(cita)
    return filas


def citas_por_recordar(ahora: datetime.datetime | None = None):
    """Programadas, sin recordatorio, que empiezan en las próximas RECORDATORIO_HORAS_ANTES."""
    ahora = ahora or timezone.now()
    limite = ahora + datetime.timedelta(hours=settings.RECORDATORIO_HORAS_ANTES)
    return Cita.objects.filter(
        estado=EstadoCita.PROGRAMADA,
        recordatorio_enviado=False,
        fecha_hora__gt=ahora,
        fecha_hora__lte=limite,
    ).order_by('fecha_hora')


def programar_recordatorios(ahora: datetime.datetime | None = None) -> int:
    """Lo corre el comando `enviar_recordatorios`. Devuelve cuántas citas se recordaron."""
    return sum(bool(enviar_recordatorio(cita)) for cita in citas_por_recordar(ahora))


@transaction.atomic
def notificar_resultados(estudios) -> list[Notificacion]:
    """
    Lo llama `pedidos.services.enviar_resultados`. Una fila por estudio y canal; el worker
    junta los de un mismo envío en un solo mensaje con un solo PDF.
    """
    estudios = list(estudios)
    persona = estudios[0].pedido.cita.paciente.persona
    return _crear(TipoNotificacion.RESULTADOS, _destinatarios_o_error(persona), estudios=estudios)


# Lo que escribe el worker


def marcar_enviada(notificacion: Notificacion) -> None:
    notificacion.estado = EstadoNotificacion.ENVIADO
    notificacion.error = ''
    notificacion.fecha_envio = timezone.now()
    notificacion.save(update_fields=['estado', 'error', 'fecha_envio'])


def marcar_fallida(notificacion: Notificacion, error: str) -> None:
    notificacion.estado = EstadoNotificacion.FALLIDO
    notificacion.error = error[:1000]
    notificacion.save(update_fields=['estado', 'error'])
