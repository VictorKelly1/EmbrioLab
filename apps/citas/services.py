import datetime

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.citas.models import DURACION, Cita, EstadoCita, OrigenCita
from apps.citas.tokens import hash_token, nuevo_token
from apps.cuentas.models import Recepcionista
from apps.pacientes.models import Paciente


class TransicionInvalida(ValidationError):
    """Cambio de estado no permitido para la cita."""


class TokenInvalido(Exception):
    """El link no existe, ya se usó o ya venció. No se distingue el motivo a propósito."""


def _empalme(fecha_hora: datetime.datetime, excluir: int | None = None) -> Cita | None:
    citas = Cita.objects.filter(fecha_hora__lt=fecha_hora + DURACION, fecha_fin__gt=fecha_hora)
    if excluir:
        citas = citas.exclude(pk=excluir)
    return citas.first()


def _mensaje_empalme(cita: Cita) -> str:
    hora = timezone.localtime(cita.fecha_hora).strftime('%H:%M')
    return f'Ya hay una cita a las {hora} que ocupa ese horario.'


def _guardar(cita: Cita) -> Cita:
    """Guarda validando empalmes; la restricción de la BD cubre las altas simultáneas."""
    otra = _empalme(cita.fecha_hora, excluir=cita.pk)
    if otra:
        raise ValidationError({'fecha_hora': _mensaje_empalme(otra)})
    cita.full_clean(exclude=['fecha_fin', 'recepcionista', 'paciente'], validate_constraints=False)
    try:
        with transaction.atomic():
            cita.save()
    except IntegrityError as error:
        if 'cita_sin_empalmes' in str(error):
            raise ValidationError({'fecha_hora': 'Ya hay una cita en ese horario.'}) from error
        raise
    return cita


def _validar_paciente(paciente: Paciente) -> None:
    if not paciente.estado_actividad:
        raise ValidationError({'paciente': 'El paciente está dado de baja; reactívelo primero.'})


def _validar_futuro(fecha_hora: datetime.datetime) -> None:
    if fecha_hora < timezone.now():
        raise ValidationError({'fecha_hora': 'Elija una fecha y hora futuras.'})


def _validar_programada(cita: Cita, accion: str) -> None:
    if cita.estado != EstadoCita.PROGRAMADA:
        raise TransicionInvalida(
            f'No se puede {accion} una cita {cita.get_estado_display().lower()}.'
        )


@transaction.atomic
def agendar_cita(
    *,
    recepcionista: Recepcionista,
    paciente: Paciente,
    fecha_hora: datetime.datetime,
    asunto: str = '',
) -> Cita:
    _validar_paciente(paciente)
    _validar_futuro(fecha_hora)
    return _guardar(
        Cita(
            recepcionista=recepcionista,
            paciente=paciente,
            fecha_hora=fecha_hora.replace(second=0, microsecond=0),
            asunto=asunto.strip(),
            origen=OrigenCita.AGENDADA,
            numero_folio=paciente.folio,
        )
    )


@transaction.atomic
def registrar_espontanea(
    *,
    recepcionista: Recepcionista,
    paciente: Paciente,
    asunto: str = '',
    fecha_hora: datetime.datetime | None = None,
) -> Cita:
    """Paciente que llega sin cita: se crea la cita ya atendida, por defecto a esta hora."""
    _validar_paciente(paciente)
    fecha_hora = fecha_hora or timezone.now()
    return _guardar(
        Cita(
            recepcionista=recepcionista,
            paciente=paciente,
            fecha_hora=fecha_hora.replace(second=0, microsecond=0),
            asunto=asunto.strip(),
            origen=OrigenCita.ESPONTANEA,
            estado=EstadoCita.ATENDIDA,
            numero_folio=paciente.folio,
        )
    )


@transaction.atomic
def reprogramar_cita(cita: Cita, *, fecha_hora: datetime.datetime) -> Cita:
    _validar_programada(cita, 'reprogramar')
    _validar_futuro(fecha_hora)
    cita.fecha_hora = fecha_hora.replace(second=0, microsecond=0)
    if cita.token_qr:
        cita.token_expiracion = _expiracion(cita)
    # El recordatorio se manda 24 h antes de la fecha nueva.
    cita.recordatorio_enviado = False
    return _guardar(cita)


@transaction.atomic
def cancelar_cita(cita: Cita) -> None:
    """Las citas canceladas no se guardan (CONTEXTO.md §3)."""
    _validar_programada(cita, 'cancelar')
    cita.delete()


@transaction.atomic
def marcar_atendida(cita: Cita) -> Cita:
    _validar_programada(cita, 'marcar como atendida')
    cita.estado = EstadoCita.ATENDIDA
    cita.save(update_fields=['estado', 'actualizado_en'])
    return cita


@transaction.atomic
def marcar_no_atendida(cita: Cita) -> Cita:
    _validar_programada(cita, 'marcar como no atendida')
    if cita.fecha_hora > timezone.now():
        raise TransicionInvalida('La cita todavía no empieza.')
    cita.estado = EstadoCita.NO_ATENDIDA
    cita.save(update_fields=['estado', 'actualizado_en'])
    return cita


@transaction.atomic
def marcar_recordatorio_enviado(cita: Cita) -> Cita:
    """Lo llama notificaciones al crear el recordatorio: no se vuelve a mandar."""
    cita.recordatorio_enviado = True
    cita.save(update_fields=['recordatorio_enviado', 'actualizado_en'])
    return cita


# Token del formulario (QR)


def tiene_formulario_llenado(cita: Cita) -> bool:
    try:
        cita.formulario_llenado  # noqa: B018  relación inversa de formularios
    except ObjectDoesNotExist:
        return False
    return True


def _expiracion(cita: Cita) -> datetime.datetime:
    vigencia = datetime.timedelta(hours=settings.CITAS_QR_HORAS_VIGENCIA)
    return max(timezone.now(), cita.fecha_hora) + vigencia


@transaction.atomic
def generar_token_qr(cita: Cita) -> str:
    """
    Devuelve el token en claro para armar el link/QR; en la BD solo queda su hash.
    Generar uno nuevo invalida el anterior.
    """
    if cita.estado == EstadoCita.NO_ATENDIDA:
        raise TransicionInvalida('La cita no fue atendida.')
    if tiene_formulario_llenado(cita):
        raise TransicionInvalida('El paciente ya llenó el formulario de esta cita.')
    token = nuevo_token()
    cita.token_qr = hash_token(token)
    cita.token_expiracion = _expiracion(cita)
    cita.save(update_fields=['token_qr', 'token_expiracion', 'actualizado_en'])
    return token


def obtener_cita_por_token(token: str) -> Cita:
    """La cita de un token vigente y sin usar; si no, TokenInvalido."""
    if not token:
        raise TokenInvalido
    cita = (
        Cita.objects.select_related('paciente__persona')
        .filter(token_qr=hash_token(token), token_expiracion__gt=timezone.now())
        .first()
    )
    if cita is None:
        raise TokenInvalido
    return cita


@transaction.atomic
def consumir_token(cita: Cita) -> None:
    """Un solo uso: tras llenar el formulario el token deja de servir."""
    cita.token_qr = ''
    cita.token_expiracion = None
    cita.save(update_fields=['token_qr', 'token_expiracion', 'actualizado_en'])
