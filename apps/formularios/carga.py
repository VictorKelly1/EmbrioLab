"""
Formularios desde archivos JSON (`apps/formularios/datos/`).

Cada versión de un formulario vive en un archivo, por ejemplo `hombre_v2.json`:

    {
      "formulario": {
        "nombre": "Formulario de la visita — hombre",
        "descripcion": "…",
        "genero_aplicable": "masculino"      # "masculino", "femenino" o "" (todos)
      },
      "esquema": {"secciones": [...]}        # formato en formularios/esquema.py
    }

El flujo para cargar los del cliente (README, «Formularios del cliente»):
1. Se escribe el archivo y se revisa con `manage.py revisar_formulario <archivo> --html`
   (valida, dice qué cambia frente a lo publicado y genera una vista previa).
2. Se publica con una migración de datos que llama a `publicar()` (CONTEXTO.md §5: los
   formularios se cargan con migraciones, así llegan iguales a todos los entornos).

Un archivo que ya usa una migración NO se edita: cada cambio es un archivo nuevo
(`_v3.json`) y otra migración. Así una base nueva repite exactamente la misma historia.
"""

import json
from dataclasses import dataclass
from pathlib import Path

from django.core.exceptions import ValidationError
from django.db.models import Max
from django.utils import timezone

from apps.formularios.esquema import preguntas, validar_esquema

DATOS = Path(__file__).resolve().parent / 'datos'
GENEROS = ('masculino', 'femenino', '')


@dataclass(frozen=True)
class DefinicionFormulario:
    nombre: str
    descripcion: str
    genero_aplicable: str
    esquema: dict


def leer(ruta: str | Path) -> DefinicionFormulario:
    """Lee y valida un archivo. Lanza ValidationError con todos los problemas."""
    ruta = Path(ruta)
    try:
        datos = json.loads(ruta.read_text(encoding='utf-8'))
    except FileNotFoundError as error:
        raise ValidationError(f'No existe el archivo {ruta}.') from error
    except json.JSONDecodeError as error:
        raise ValidationError(
            f'{ruta.name} no es JSON válido (línea {error.lineno}, columna {error.colno}): '
            f'{error.msg}.'
        ) from error

    if not isinstance(datos, dict) or set(datos) != {'formulario', 'esquema'}:
        raise ValidationError('El archivo debe ser {"formulario": {...}, "esquema": {...}}.')
    formulario = datos['formulario']
    if not isinstance(formulario, dict) or set(formulario) - {
        'nombre',
        'descripcion',
        'genero_aplicable',
    }:
        raise ValidationError(
            '"formulario" solo admite "nombre", "descripcion" y "genero_aplicable".'
        )
    errores = []
    nombre = formulario.get('nombre')
    if not isinstance(nombre, str) or not nombre.strip():
        errores.append('Falta "formulario.nombre".')
    elif len(nombre.strip()) > 150:
        errores.append('"formulario.nombre" admite hasta 150 caracteres.')
    descripcion = formulario.get('descripcion', '')
    if not isinstance(descripcion, str):
        errores.append('"formulario.descripcion" debe ser texto.')
    genero = formulario.get('genero_aplicable', '')
    if genero not in GENEROS:
        errores.append('"formulario.genero_aplicable" debe ser "masculino", "femenino" o "".')
    try:
        validar_esquema(datos['esquema'])
    except ValidationError as error:
        errores.extend(error.messages)
    if errores:
        raise ValidationError(errores)
    return DefinicionFormulario(
        nombre=nombre.strip(),
        descripcion=descripcion.strip(),
        genero_aplicable=genero,
        esquema=datos['esquema'],
    )


def formulario_de(definicion: DefinicionFormulario, *, Formulario):
    """
    El formulario activo que esta definición actualiza: el de su género. En la Fase 1 hay
    uno por género (CONTEXTO.md §2), así que el nombre puede cambiar sin crear otro.
    """
    activos = list(
        Formulario.objects.filter(activo=True, genero_aplicable=definicion.genero_aplicable)
    )
    if len(activos) > 1:
        raise ValidationError(
            f'Hay {len(activos)} formularios activos para el mismo género; '
            'no se sabe cuál actualizar.'
        )
    return activos[0] if activos else None


def publicar(
    definicion: DefinicionFormulario, *, Formulario, VersionFormulario
) -> tuple[object, bool]:
    """
    Publica la definición como versión nueva del formulario de su género (lo crea si no
    existe) y despublica la anterior. Devuelve (versión publicada, si es nueva).

    Si el esquema es igual al publicado no crea nada: se puede correr dos veces.

    Recibe los modelos como argumentos para poder usarse en migraciones de datos con
    `apps.get_model(...)`. Fuera de las migraciones, use los modelos de siempre.
    """
    formulario = formulario_de(definicion, Formulario=Formulario)
    if formulario is None:
        formulario = Formulario.objects.create(
            nombre=definicion.nombre,
            descripcion=definicion.descripcion,
            genero_aplicable=definicion.genero_aplicable,
        )
    else:
        # Bloquea el formulario para que dos publicaciones simultáneas no choquen.
        formulario = Formulario.objects.select_for_update().get(pk=formulario.pk)
        if (formulario.nombre, formulario.descripcion) != (
            definicion.nombre,
            definicion.descripcion,
        ):
            formulario.nombre = definicion.nombre
            formulario.descripcion = definicion.descripcion
            formulario.save(update_fields=['nombre', 'descripcion'])

    versiones = VersionFormulario.objects.filter(formulario=formulario)
    actual = versiones.filter(publicada=True).first()
    if actual is not None and actual.esquema == definicion.esquema:
        return actual, False
    ultima = versiones.aggregate(n=Max('numero_version'))['n'] or 0
    versiones.filter(publicada=True).update(publicada=False)
    nueva = VersionFormulario.objects.create(
        formulario=formulario,
        numero_version=ultima + 1,
        esquema=definicion.esquema,
        publicada=True,
        fecha_publicacion=timezone.now(),
    )
    return nueva, True


@dataclass(frozen=True)
class Diferencias:
    agregadas: list[str]
    quitadas: list[str]
    cambiadas: list[str]

    @property
    def hay(self) -> bool:
        return bool(self.agregadas or self.quitadas or self.cambiadas)


def diferencias(anterior: dict | None, nuevo: dict) -> Diferencias:
    """Preguntas agregadas, quitadas y cambiadas (por clave) entre dos esquemas."""
    antes = {p['clave']: p for p in preguntas(anterior)} if anterior else {}
    despues = {p['clave']: p for p in preguntas(nuevo)}
    return Diferencias(
        agregadas=[c for c in despues if c not in antes],
        quitadas=[c for c in antes if c not in despues],
        cambiadas=[c for c in despues if c in antes and antes[c] != despues[c]],
    )
