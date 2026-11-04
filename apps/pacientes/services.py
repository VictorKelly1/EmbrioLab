from django.core.exceptions import ValidationError
from django.db import connection, transaction

from apps.pacientes.models import SECUENCIA_NUMERO, Doctor, Paciente
from apps.personas.models import Persona
from apps.personas.selectors import contactos_principales
from apps.personas.services import (
    actualizar_persona,
    crear_persona,
    guardar_contactos_principales,
    guardar_direccion,
)

# Decidido con el cliente: sin correo ni WhatsApp no se le pueden enviar resultados.
CONTACTOS_DE_ENVIO = ('correo', 'whatsapp')
FALTA_CONTACTO = 'Escriba al menos un correo o un WhatsApp.'


def _exigir_contacto(contactos: dict[str, str], actuales: dict[str, str] | None = None) -> None:
    """
    Exige un correo o WhatsApp. `actuales` son los que ya tiene: cuentan si `contactos`
    no los cambia.
    """
    finales = {**(actuales or {}), **contactos}
    if not any((finales.get(tipo) or '').strip() for tipo in CONTACTOS_DE_ENVIO):
        raise ValidationError({tipo: FALTA_CONTACTO for tipo in CONTACTOS_DE_ENVIO})


def _siguiente_numero() -> int:
    with connection.cursor() as cursor:
        cursor.execute('SELECT nextval(%s)', [SECUENCIA_NUMERO])
        return cursor.fetchone()[0]


@transaction.atomic
def registrar_paciente(
    *,
    datos_persona: dict,
    contactos: dict[str, str] | None = None,
    direccion: dict | None = None,
    foto=None,
) -> Paciente:
    """Registra a la persona como paciente con su número, contactos y dirección."""
    _exigir_contacto(contactos or {})
    curp = (datos_persona.get('curp') or '').strip().upper()
    existente = Paciente.objects.filter(persona__curp=curp).first()
    if existente:
        raise ValidationError(
            {'curp': f'Ya hay un paciente con esta CURP (número {existente.numero}).'}
        )

    persona = crear_persona(**datos_persona, foto=foto)
    guardar_contactos_principales(persona, contactos or {})
    guardar_direccion(persona, direccion)

    paciente = Paciente(persona=persona, numero=_siguiente_numero())
    paciente.full_clean()
    paciente.save()
    return paciente


@transaction.atomic
def actualizar_paciente(
    paciente: Paciente,
    *,
    datos_persona: dict,
    contactos: dict[str, str] | None = None,
    direccion: dict | None = None,
    foto=None,
) -> Paciente:
    """`foto`: None la deja igual, False la quita y un archivo la reemplaza."""
    persona: Persona = paciente.persona
    _exigir_contacto(contactos or {}, contactos_principales(persona))
    actualizar_persona(persona, foto=foto, **datos_persona)
    guardar_contactos_principales(persona, contactos or {})
    guardar_direccion(persona, direccion)
    return paciente


def _guardar_doctor(
    doctor: Doctor, nombre: str, correo: str, whatsapp: str, contacto: str
) -> Doctor:
    doctor.nombre = ' '.join(nombre.split())
    doctor.correo = correo.strip().lower()
    doctor.whatsapp = whatsapp.strip()
    doctor.contacto = contacto.strip()
    _exigir_contacto({'correo': doctor.correo, 'whatsapp': doctor.whatsapp})
    doctor.full_clean()
    doctor.save()
    return doctor


@transaction.atomic
def crear_doctor(
    *, nombre: str, correo: str = '', whatsapp: str = '', contacto: str = ''
) -> Doctor:
    """Lo hacen la recepción y los químicos (cambio del cliente, 2026-11-03)."""
    return _guardar_doctor(Doctor(), nombre, correo, whatsapp, contacto)


@transaction.atomic
def actualizar_doctor(
    doctor: Doctor, *, nombre: str, correo: str = '', whatsapp: str = '', contacto: str = ''
) -> Doctor:
    return _guardar_doctor(doctor, nombre, correo, whatsapp, contacto)
