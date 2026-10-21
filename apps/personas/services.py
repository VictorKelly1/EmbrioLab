from django.db import transaction

from apps.personas.models import Persona


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
) -> Persona:
    persona = Persona(
        nombre=nombre.strip(),
        apellido_paterno=apellido_paterno.strip(),
        apellido_materno=apellido_materno.strip(),
        genero=genero,
        fecha_nacimiento=fecha_nacimiento,
        curp=curp.strip().upper(),
        numero_ine=numero_ine.strip(),
        direccion=direccion,
    )
    persona.full_clean()
    persona.save()
    return persona
