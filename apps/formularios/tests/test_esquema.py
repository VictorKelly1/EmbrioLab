import copy

import pytest
from django.core.exceptions import ValidationError

from apps.formularios.esquema import validar_esquema
from apps.formularios.tests.factories import ESQUEMA_MINIMO


def _con_pregunta(**pregunta):
    esquema = copy.deepcopy(ESQUEMA_MINIMO)
    esquema['secciones'][0]['preguntas'].append(pregunta)
    return esquema


def _errores(esquema):
    with pytest.raises(ValidationError) as error:
        validar_esquema(esquema)
    return ' '.join(error.value.messages)


def test_esquema_valido():
    validar_esquema(ESQUEMA_MINIMO)


@pytest.mark.parametrize('esquema', [None, [], {}, {'secciones': []}, {'secciones': [], 'otra': 1}])
def test_estructura_raiz(esquema):
    with pytest.raises(ValidationError):
        validar_esquema(esquema)


@pytest.mark.parametrize(
    ('pregunta', 'mensaje'),
    [
        ({'clave': 'Mal Clave', 'etiqueta': 'x', 'tipo': 'texto'}, '"clave"'),
        ({'clave': 'ayuno', 'etiqueta': 'x', 'tipo': 'texto'}, 'repetida'),
        ({'clave': 'x', 'etiqueta': ' ', 'tipo': 'texto'}, 'falta "etiqueta"'),
        ({'clave': 'x', 'etiqueta': 'x', 'tipo': 'archivo'}, '"tipo"'),
        ({'clave': 'x', 'etiqueta': 'x', 'tipo': 'texto', 'min': 1}, 'no válidas'),
        ({'clave': 'x', 'etiqueta': 'x', 'tipo': 'opcion', 'opciones': ['solo']}, 'al menos 2'),
        ({'clave': 'x', 'etiqueta': 'x', 'tipo': 'opcion', 'opciones': ['a', 'a']}, 'repetidas'),
        ({'clave': 'x', 'etiqueta': 'x', 'tipo': 'numero', 'min': 5, 'max': 1}, 'mayor que'),
        ({'clave': 'x', 'etiqueta': 'x', 'tipo': 'numero', 'decimales': 9}, 'decimales'),
        ({'clave': 'x', 'etiqueta': 'x', 'tipo': 'texto', 'obligatoria': 'si'}, 'true o false'),
        (
            {
                'clave': 'x',
                'etiqueta': 'x',
                'tipo': 'texto',
                'mostrar_si': {'clave': 'zzz', 'valor': 1},
            },
            'pregunta anterior',
        ),
        (
            {
                'clave': 'x',
                'etiqueta': 'x',
                'tipo': 'texto',
                'mostrar_si': {'clave': 'ayuno', 'valor': 'sí'},
            },
            'true o false',
        ),
        (
            {
                'clave': 'x',
                'etiqueta': 'x',
                'tipo': 'texto',
                'mostrar_si': {'clave': 'notas', 'valor': 'a'},
            },
            'sí/no u opción',
        ),
    ],
)
def test_errores_de_preguntas(pregunta, mensaje):
    assert mensaje in _errores(_con_pregunta(**pregunta))


def test_reporta_todos_los_errores_juntos():
    esquema = _con_pregunta(clave='X', etiqueta='', tipo='texto')
    with pytest.raises(ValidationError) as error:
        validar_esquema(esquema)
    assert len(error.value.messages) == 2


def test_condicion_con_opcion():
    esquema = _con_pregunta(clave='fuma', etiqueta='¿Fuma?', tipo='opcion', opciones=['No', 'Sí'])
    esquema['secciones'][0]['preguntas'].append(
        {
            'clave': 'cuanto',
            'etiqueta': '¿Cuánto?',
            'tipo': 'texto',
            'mostrar_si': {'clave': 'fuma', 'valor': 'Sí'},
        }
    )
    validar_esquema(esquema)
    esquema['secciones'][0]['preguntas'][-1]['mostrar_si']['valor'] = 'Tal vez'
    assert 'no es una de las opciones' in _errores(esquema)
