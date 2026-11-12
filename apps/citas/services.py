import datetime
from dataclasses import dataclass

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.core.validators import EmailValidator, RegexValidator
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.citas.models import DURACION, Cita, EstadoCita, OrigenCita
from apps.citas.tokens import hash_token, nuevo_token
from apps.cuentas.models import Recepcionista
from apps.pacientes.models import Paciente
from apps.pacientes.services import registrar_paciente
from apps.personas.models import TELEFONO_REGEX, Genero


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


@dataclass(frozen=True)
class SinRegistro:
    """
    Quien agenda sin estar registrado como paciente (CONTEXTO.md §3): lo mínimo para
    reconocerlo al llegar, elegir su formulario y mandarle el recordatorio.
    """

    nombre: str
    apellido_paterno: str
    genero: str
    telefono: str = ''
    correo: str = ''


def _limpiar_sin_registro(datos: SinRegistro) -> SinRegistro:
    errores = {}
    nombre = ' '.join(datos.nombre.split())
    apellido = ' '.join(datos.apellido_paterno.split())
    telefono = ''.join(datos.telefono.split())
    correo = datos.correo.strip().lower()
    if not nombre:
        errores['nombre'] = 'Escriba el nombre.'
    if not apellido:
        errores['apellido_paterno'] = 'Escriba el apellido paterno.'
    if datos.genero not in Genero.values:
        errores['genero'] = 'Elija el género: con él se elige el formulario de la visita.'
    if telefono:
        try:
            RegexValidator(TELEFONO_REGEX)(telefono)
        except ValidationError:
            errores['telefono'] = 'Escriba el número con lada: 10 dígitos (o +código de país).'
    if correo:
        try:
            EmailValidator()(correo)
        except ValidationError:
            errores['correo'] = 'Escriba un correo válido.'
    if not telefono and not correo and 'telefono' not in errores:
        errores['telefono'] = 'Escriba un teléfono o un correo para el recordatorio.'
    if errores:
        raise ValidationError(errores)
    return SinRegistro(nombre, apellido, datos.genero, telefono, correo)


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
    fecha_hora: datetime.datetime,
    paciente: Paciente | None = None,
    sin_registro: SinRegistro | None = None,
    asunto: str = '',
) -> Cita:
    """
    Con un paciente registrado o, si todavía no lo está, con los datos de `sin_registro`
    (CONTEXTO.md §3). El paciente se registra cuando llega (`registrar_llegada`).
    """
    if (paciente is None) == (sin_registro is None):
        raise ValidationError('Elija a un paciente registrado o escriba los datos de quien agenda.')
    cita = Cita(
        recepcionista=recepcionista,
        fecha_hora=fecha_hora.replace(second=0, microsecond=0),
        asunto=asunto.strip(),
        origen=OrigenCita.AGENDADA,
    )
    if paciente is not None:
        _validar_paciente(paciente)
        cita.paciente = paciente
        cita.numero_folio = paciente.folio
    else:
        datos = _limpiar_sin_registro(sin_registro)
        cita.nombre = datos.nombre
        cita.apellido_paterno = datos.apellido_paterno
        cita.genero = datos.genero
        cita.telefono = datos.telefono
        cita.correo = datos.correo
    _validar_futuro(fecha_hora)
    return _guardar(cita)


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
    if cita.paciente_id is None:
        raise ValidationError(
            'Esta cita se agendó sin registro: registre la llegada del paciente para atenderla.'
        )
    cita.estado = EstadoCita.ATENDIDA
    cita.save(update_fields=['estado', 'actualizado_en'])
    return cita


@transaction.atomic
def registrar_llegada(cita: Cita, paciente: Paciente) -> Cita:
    """
    Llegó quien agendó sin registro: la cita queda ligada a su paciente (que ya existía
    o que se acaba de registrar), con su folio, y atendida (CONTEXTO.md §3).
    """
    cita = Cita.objects.select_for_update().get(pk=cita.pk)
    _validar_programada(cita, 'registrar la llegada de')
    if cita.paciente_id is not None:
        raise ValidationError('Esta cita ya tiene paciente: márquela como atendida.')
    _validar_paciente(paciente)
    cita.paciente = paciente
    cita.numero_folio = paciente.folio
    cita.estado = EstadoCita.ATENDIDA
    cita.save(update_fields=['paciente', 'numero_folio', 'estado', 'actualizado_en'])
    return cita


@transaction.atomic
def registrar_paciente_y_llegada(cita: Cita, **datos_paciente) -> Paciente:
    """Registra al paciente nuevo y su llegada en una sola transacción: todo o nada."""
    paciente = registrar_paciente(**datos_paciente)
    registrar_llegada(cita, paciente)
    return paciente


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
