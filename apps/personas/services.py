import re

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.personas.models import Contacto, Direccion, Persona, TipoContacto

CAMPOS_PERSONA = (
    'nombre',
    'apellido_paterno',
    'apellido_materno',
    'genero',
    'fecha_nacimiento',
    'curp',
    'numero_ine',
)
CAMPOS_DIRECCION = (
    'calle',
    'numero',
    'colonia_frac',
    'ciudad',
    'estado',
    'pais',
    'codigo_postal',
)


def _limpiar_persona(datos: dict) -> dict:
    limpios = {}
    for campo, valor in datos.items():
        if isinstance(valor, str):
            valor = valor.strip()
        if campo == 'curp':
            valor = valor.upper()
        limpios[campo] = valor
    return limpios


@transaction.atomic
def crear_persona(
    *,
    nombre: str,
    apellido_paterno: str,
    apellido_materno: str = '',
    genero: str,
    fecha_nacimiento,
    curp: str,
    numero_ine: str = '',
    direccion=None,
    foto=None,
) -> Persona:
    persona = Persona(
        direccion=direccion,
        **_limpiar_persona(
            {
                'nombre': nombre,
                'apellido_paterno': apellido_paterno,
                'apellido_materno': apellido_materno,
                'genero': genero,
                'fecha_nacimiento': fecha_nacimiento,
                'curp': curp,
                'numero_ine': numero_ine,
            }
        ),
    )
    if foto:
        persona.foto = foto
    persona.full_clean()
    persona.save()
    return persona


@transaction.atomic
def actualizar_persona(persona: Persona, *, foto=None, **campos) -> Persona:
    """
    Cambia los datos de identidad indicados en `campos`.

    `foto`: None la deja igual, False la quita y un archivo la reemplaza.
    """
    desconocidos = set(campos) - set(CAMPOS_PERSONA)
    if desconocidos:
        raise ValueError(f'Campos no editables: {", ".join(sorted(desconocidos))}.')
    for campo, valor in _limpiar_persona(campos).items():
        setattr(persona, campo, valor)

    foto_anterior = persona.foto.name if persona.foto else ''
    if foto is False:
        persona.foto = None
    elif foto:
        persona.foto = foto

    persona.full_clean()
    persona.save()

    if foto_anterior and foto_anterior != persona.foto.name:
        almacenamiento = persona.foto.storage
        transaction.on_commit(lambda: almacenamiento.delete(foto_anterior))
    return persona


@transaction.atomic
def guardar_direccion(persona: Persona, datos: dict | None) -> Direccion | None:
    """
    Asigna la dirección de la persona. Sin datos, la persona se queda sin dirección.

    Las direcciones se pueden compartir: si la actual la usa alguien más, se crea una
    nueva en lugar de modificarla.
    """
    datos = {c: (datos or {}).get(c, '').strip() for c in CAMPOS_DIRECCION}
    if not any(v for c, v in datos.items() if c != 'pais'):
        persona.direccion = None
        persona.save(update_fields=['direccion', 'actualizado_en'])
        return None
    datos['pais'] = datos['pais'] or 'México'

    direccion = persona.direccion
    if direccion is None or direccion.personas.exclude(pk=persona.pk).exists():
        direccion = Direccion()
    for campo, valor in datos.items():
        setattr(direccion, campo, valor)
    direccion.full_clean()
    direccion.save()

    if persona.direccion_id != direccion.pk:
        persona.direccion = direccion
        persona.save(update_fields=['direccion', 'actualizado_en'])
    return direccion


def _normalizar_contacto(tipo: str, valor: str) -> str:
    valor = valor.strip()
    if tipo == TipoContacto.CORREO:
        return valor.lower()
    # Quita espacios, guiones y paréntesis: '(33) 1234-5678' → '3312345678'.
    return re.sub(r'[\s\-().]', '', valor)


@transaction.atomic
def guardar_contactos_principales(persona: Persona, valores: dict[str, str]) -> None:
    """
    Fija el contacto principal de cada tipo indicado ({tipo: valor}).
    Un valor vacío quita el principal de ese tipo.
    """
    errores = {}
    for tipo, valor in valores.items():
        if tipo not in TipoContacto.values:
            raise ValueError(f'Tipo de contacto desconocido: {tipo}.')
        valor = _normalizar_contacto(tipo, valor or '')
        actual = persona.contactos.filter(tipo=tipo, principal=True).first()

        if not valor:
            if actual:
                actual.delete()
            continue
        if actual and actual.valor == valor:
            continue

        persona.contactos.filter(tipo=tipo, valor=valor, principal=False).delete()
        contacto = actual or Contacto(persona=persona, tipo=tipo, principal=True)
        contacto.valor = valor
        try:
            contacto.full_clean()
        except ValidationError as error:
            errores[tipo] = error.message_dict.get('valor', error.messages)
            continue
        contacto.save()

    if errores:
        raise ValidationError(errores)
