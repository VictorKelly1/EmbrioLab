from decimal import Decimal

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction

from apps.cuentas.models import MODELOS_ROL, Rol, Usuario
from apps.personas.models import Persona
from apps.personas.services import crear_persona


@transaction.atomic
def crear_usuario(
    *,
    persona: Persona,
    correo: str,
    password: str,
    rol: str,
    sueldo: Decimal,
    cedula_profesional: str = '',
    color: str | None = None,
    nombre_usuario: str = '',
) -> Usuario:
    """Crea un usuario con exactamente un rol (Fase 1)."""
    if rol not in MODELOS_ROL:
        raise ValidationError({'rol': f'Rol desconocido: {rol}.'})
    if rol == Rol.QUIMICO and not cedula_profesional.strip():
        raise ValidationError({'cedula_profesional': 'Es obligatoria para un químico.'})

    campos = {'persona': persona, 'nombre_usuario': nombre_usuario}
    if color:
        campos['color'] = color
    usuario = Usuario(correo=correo.strip().lower(), **campos)
    try:
        validate_password(password, usuario)
    except ValidationError as error:
        raise ValidationError({'password': error.messages}) from error
    usuario.set_password(password)
    usuario.full_clean()
    usuario.save()

    datos_rol = {'usuario': usuario, 'sueldo': sueldo}
    if rol == Rol.QUIMICO:
        datos_rol['cedula_profesional'] = cedula_profesional.strip()
    fila = MODELOS_ROL[rol](**datos_rol)
    fila.full_clean()
    fila.save()
    return usuario


@transaction.atomic
def registrar_usuario(*, datos_persona: dict, **datos_usuario) -> Usuario:
    """Crea la persona y su usuario con un rol. Los argumentos son los de crear_usuario."""
    persona = crear_persona(**datos_persona)
    return crear_usuario(persona=persona, **datos_usuario)
