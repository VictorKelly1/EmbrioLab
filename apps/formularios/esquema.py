"""
Formato del esquema JSON de un formulario y su validador.

    {
      "secciones": [
        {
          "titulo": "Su visita",
          "preguntas": [
            {"clave": "dias_abstinencia", "etiqueta": "¿Cuántos días…?", "tipo": "numero",
             "obligatoria": true, "min": 0, "max": 30, "ayuda": "…"},
            {"clave": "medicamento", "etiqueta": "¿Toma algún medicamento?", "tipo": "si_no"},
            {"clave": "medicamento_cual", "etiqueta": "¿Cuál?", "tipo": "texto",
             "obligatoria": true, "mostrar_si": {"clave": "medicamento", "valor": true}}
          ]
        }
      ]
    }

Tipos: texto, texto_largo, numero (con `decimales`, `min`, `max`), si_no, opcion y
opciones (con `opciones`), fecha (con `no_futura`). `mostrar_si` muestra la pregunta
solo si otra pregunta anterior tiene ese valor; si no se muestra, no es obligatoria.
"""

import re

from django.core.exceptions import ValidationError

TIPOS = ('texto', 'texto_largo', 'numero', 'si_no', 'opcion', 'opciones', 'fecha')
CLAVE_REGEX = re.compile(r'^[a-z][a-z0-9_]{0,49}$')

_LLAVES = {
    'comunes': {'clave', 'etiqueta', 'tipo', 'obligatoria', 'ayuda', 'mostrar_si'},
    'texto': set(),
    'texto_largo': set(),
    'numero': {'decimales', 'min', 'max'},
    'si_no': set(),
    'opcion': {'opciones'},
    'opciones': {'opciones'},
    'fecha': {'no_futura'},
}


def _es_numero(valor) -> bool:
    return isinstance(valor, int | float) and not isinstance(valor, bool)


def _validar_pregunta(pregunta, ruta: str, anteriores: dict, errores: list[str]) -> None:
    if not isinstance(pregunta, dict):
        errores.append(f'{ruta}: debe ser un objeto.')
        return
    clave = pregunta.get('clave')
    if not isinstance(clave, str) or not CLAVE_REGEX.match(clave):
        errores.append(f'{ruta}: "clave" debe ser minúsculas, números y _ (máx. 50).')
        clave = None
    elif clave in anteriores:
        errores.append(f'{ruta}: la clave "{clave}" está repetida.')
    ruta = f'{ruta} ({clave})' if clave else ruta

    etiqueta = pregunta.get('etiqueta')
    if not isinstance(etiqueta, str) or not etiqueta.strip():
        errores.append(f'{ruta}: falta "etiqueta".')

    tipo = pregunta.get('tipo')
    if tipo not in TIPOS:
        errores.append(f'{ruta}: "tipo" debe ser uno de {", ".join(TIPOS)}.')
        return

    sobrantes = set(pregunta) - _LLAVES['comunes'] - _LLAVES[tipo]
    if sobrantes:
        errores.append(f'{ruta}: llaves no válidas para "{tipo}": {", ".join(sorted(sobrantes))}.')

    if 'obligatoria' in pregunta and not isinstance(pregunta['obligatoria'], bool):
        errores.append(f'{ruta}: "obligatoria" debe ser true o false.')
    if 'ayuda' in pregunta and not isinstance(pregunta['ayuda'], str):
        errores.append(f'{ruta}: "ayuda" debe ser texto.')

    if tipo in ('opcion', 'opciones'):
        opciones = pregunta.get('opciones')
        if (
            not isinstance(opciones, list)
            or len(opciones) < 2
            or not all(isinstance(o, str) and o.strip() for o in opciones)
        ):
            errores.append(f'{ruta}: "opciones" debe ser una lista de al menos 2 textos.')
        elif len(set(opciones)) != len(opciones):
            errores.append(f'{ruta}: hay opciones repetidas.')

    if tipo == 'numero':
        decimales = pregunta.get('decimales', 0)
        if not isinstance(decimales, int) or isinstance(decimales, bool) or not 0 <= decimales <= 4:
            errores.append(f'{ruta}: "decimales" debe ser un entero de 0 a 4.')
        for limite in ('min', 'max'):
            if limite in pregunta and not _es_numero(pregunta[limite]):
                errores.append(f'{ruta}: "{limite}" debe ser un número.')
        minimo, maximo = pregunta.get('min'), pregunta.get('max')
        if _es_numero(minimo) and _es_numero(maximo) and minimo > maximo:
            errores.append(f'{ruta}: "min" es mayor que "max".')

    if tipo == 'fecha' and 'no_futura' in pregunta and not isinstance(pregunta['no_futura'], bool):
        errores.append(f'{ruta}: "no_futura" debe ser true o false.')

    if 'mostrar_si' in pregunta:
        _validar_condicion(pregunta['mostrar_si'], ruta, anteriores, errores)

    if clave:
        anteriores[clave] = pregunta


def _validar_condicion(condicion, ruta: str, anteriores: dict, errores: list[str]) -> None:
    if not isinstance(condicion, dict) or set(condicion) != {'clave', 'valor'}:
        errores.append(f'{ruta}: "mostrar_si" debe ser {{"clave": …, "valor": …}}.')
        return
    origen = anteriores.get(condicion['clave'])
    if origen is None:
        errores.append(f'{ruta}: "mostrar_si" debe referirse a una pregunta anterior.')
        return
    valor = condicion['valor']
    if origen.get('tipo') == 'si_no':
        if not isinstance(valor, bool):
            errores.append(f'{ruta}: con una pregunta sí/no, "valor" debe ser true o false.')
    elif origen.get('tipo') == 'opcion':
        if valor not in (origen.get('opciones') or []):
            errores.append(f'{ruta}: "valor" no es una de las opciones de "{condicion["clave"]}".')
    else:
        errores.append(f'{ruta}: "mostrar_si" solo funciona con preguntas sí/no u opción.')


def validar_esquema(esquema) -> None:
    """Lanza ValidationError con todos los problemas encontrados."""
    errores: list[str] = []
    if not isinstance(esquema, dict) or set(esquema) != {'secciones'}:
        raise ValidationError('El esquema debe ser {"secciones": [...]}.')
    secciones = esquema['secciones']
    if not isinstance(secciones, list) or not secciones:
        raise ValidationError('"secciones" debe ser una lista con al menos una sección.')

    anteriores: dict = {}
    for i, seccion in enumerate(secciones, start=1):
        ruta = f'Sección {i}'
        if not isinstance(seccion, dict) or set(seccion) - {'titulo', 'descripcion', 'preguntas'}:
            errores.append(f'{ruta}: solo admite "titulo", "descripcion" y "preguntas".')
            continue
        if not isinstance(seccion.get('titulo'), str) or not seccion['titulo'].strip():
            errores.append(f'{ruta}: falta "titulo".')
        preguntas = seccion.get('preguntas')
        if not isinstance(preguntas, list) or not preguntas:
            errores.append(f'{ruta}: debe tener al menos una pregunta.')
            continue
        for j, pregunta in enumerate(preguntas, start=1):
            _validar_pregunta(pregunta, f'{ruta}, pregunta {j}', anteriores, errores)

    if errores:
        raise ValidationError(errores)


def preguntas(esquema: dict) -> list[dict]:
    """Todas las preguntas en orden."""
    return [p for seccion in esquema['secciones'] for p in seccion['preguntas']]
