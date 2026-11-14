import datetime

import pytest

from apps.estudios.tests.factories import EstudioFactory
from apps.formularios.constructor import construir_formulario, respuestas_legibles
from apps.formularios.tests.factories import ESQUEMA_MINIMO

TODOS_LOS_TIPOS = {
    'secciones': [
        {
            'titulo': 'Todo',
            'preguntas': [
                {'clave': 'texto', 'etiqueta': 'Texto', 'tipo': 'texto'},
                {'clave': 'largo', 'etiqueta': 'Largo', 'tipo': 'texto_largo'},
                {'clave': 'entero', 'etiqueta': 'Entero', 'tipo': 'numero', 'min': 0, 'max': 10},
                {'clave': 'decimal', 'etiqueta': 'Decimal', 'tipo': 'numero', 'decimales': 1},
                {'clave': 'sino', 'etiqueta': 'Sí/no', 'tipo': 'si_no'},
                {'clave': 'una', 'etiqueta': 'Una', 'tipo': 'opcion', 'opciones': ['A', 'B']},
                {
                    'clave': 'varias',
                    'etiqueta': 'Varias',
                    'tipo': 'opciones',
                    'opciones': ['A', 'B', 'C'],
                },
                {'clave': 'fecha', 'etiqueta': 'Fecha', 'tipo': 'fecha', 'no_futura': True},
            ],
        }
    ]
}


def _form(esquema, datos):
    return construir_formulario(esquema)(datos)


def test_convierte_cada_tipo_a_json():
    form = _form(
        TODOS_LOS_TIPOS,
        {
            'texto': ' hola ',
            'largo': 'línea',
            'entero': '3',
            'decimal': '36.5',
            'sino': 'no',
            'una': 'B',
            'varias': ['A', 'C'],
            'fecha': '2026-10-01',
        },
    )
    assert form.is_valid(), form.errors
    assert form.respuestas() == {
        'texto': 'hola',
        'largo': 'línea',
        'entero': 3,
        'decimal': 36.5,
        'sino': False,
        'una': 'B',
        'varias': ['A', 'C'],
        'fecha': '2026-10-01',
    }


def test_vacias_no_se_guardan():
    form = _form(TODOS_LOS_TIPOS, {})
    assert form.is_valid()
    assert form.respuestas() == {}


@pytest.mark.parametrize(
    ('campo', 'valor'),
    [('entero', '11'), ('entero', '-1'), ('una', 'Z'), ('varias', ['Z']), ('decimal', '1.25')],
)
def test_valida_limites_y_opciones(campo, valor):
    form = _form(TODOS_LOS_TIPOS, {campo: valor})
    assert not form.is_valid()
    assert campo in form.errors


def test_fecha_no_futura_tambien_en_el_servidor():
    manana = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
    form = _form(TODOS_LOS_TIPOS, {'fecha': manana})
    assert not form.is_valid()
    assert form.errors['fecha'] == ['La fecha no puede ser futura.']


def test_fecha_no_futura_en_el_navegador():
    form = construir_formulario(TODOS_LOS_TIPOS)()
    assert form.fields['fecha'].widget.attrs['max'] == datetime.date.today().isoformat()


def test_condicional_obligatoria_solo_si_se_muestra():
    con_ayuno = _form(ESQUEMA_MINIMO, {'ayuno': 'si'})
    assert not con_ayuno.is_valid()
    assert 'horas' in con_ayuno.errors

    sin_ayuno = _form(ESQUEMA_MINIMO, {'ayuno': 'no', 'horas': '99'})
    assert sin_ayuno.is_valid(), sin_ayuno.errors
    # Lo escrito en una pregunta oculta se descarta, aunque fuera inválido.
    assert sin_ayuno.respuestas() == {'ayuno': False}


def test_obligatoria_sin_condicion():
    form = _form(ESQUEMA_MINIMO, {})
    assert not form.is_valid()
    assert 'ayuno' in form.errors


def test_secciones_para_la_plantilla():
    form = construir_formulario(ESQUEMA_MINIMO)()
    seccion = form.secciones[0]
    assert seccion['titulo'] == 'Visita'
    horas = seccion['campos'][1]
    assert horas['condicion_clave'] == 'ayuno'
    assert horas['condicion_valor'] == 'si'
    assert horas['condicion_descripcion'] == 'Se muestra si responde «Sí» a «¿Viene en ayuno?»'


def test_respuestas_legibles():
    respuestas = {
        'texto': 'hola',
        'sino': True,
        'varias': ['A', 'C'],
        'fecha': '2026-10-01',
        'decimal': 2.0,
    }
    assert respuestas_legibles(TODOS_LOS_TIPOS, respuestas) == [
        {'seccion': 'Todo', 'etiqueta': 'Texto', 'valor': 'hola'},
        {'seccion': 'Todo', 'etiqueta': 'Decimal', 'valor': 2},
        {'seccion': 'Todo', 'etiqueta': 'Sí/no', 'valor': 'Sí'},
        {'seccion': 'Todo', 'etiqueta': 'Varias', 'valor': 'A, C'},
        {'seccion': 'Todo', 'etiqueta': 'Fecha', 'valor': '01/10/2026'},
    ]


ESTUDIOS_Y_ACEPTACION = {
    'secciones': [
        {
            'titulo': 'Visita',
            'preguntas': [
                {'clave': 'estudios', 'etiqueta': 'Estudios', 'tipo': 'estudios'},
                {
                    'clave': 'solo_uno',
                    'etiqueta': 'Solo uno',
                    'tipo': 'estudios',
                    'claves': ['PRB_GLU'],
                },
                {
                    'clave': 'autorizo',
                    'etiqueta': 'Autorizo',
                    'tipo': 'aceptacion',
                    'obligatoria': True,
                },
            ],
        }
    ]
}


@pytest.fixture
def catalogo():
    glucosa = EstudioFactory(clave='PRB_GLU', nombre='Glucosa de prueba')
    EstudioFactory(clave='PRB_CUL', nombre='Cultivo de prueba', categoria=glucosa.categoria)
    EstudioFactory(clave='PRB_OFF', nombre='Inactivo de prueba', activo=False)
    return glucosa


@pytest.mark.django_db
def test_estudios_salen_del_catalogo_activo(catalogo):
    form = construir_formulario(ESTUDIOS_Y_ACEPTACION)()
    nombres = [valor for valor, _ in form.fields['estudios'].choices]
    assert 'Glucosa de prueba' in nombres
    assert 'Cultivo de prueba' in nombres
    assert 'Inactivo de prueba' not in nombres
    assert [v for v, _ in form.fields['solo_uno'].choices] == ['Glucosa de prueba']


@pytest.mark.django_db
def test_estudios_y_aceptacion_a_json(catalogo):
    form = _form(
        ESTUDIOS_Y_ACEPTACION,
        {'estudios': ['Glucosa de prueba', 'Cultivo de prueba'], 'autorizo': ['acepto']},
    )
    assert form.is_valid(), form.errors
    assert form.respuestas() == {
        'estudios': ['Glucosa de prueba', 'Cultivo de prueba'],
        'autorizo': True,
    }
    assert respuestas_legibles(ESTUDIOS_Y_ACEPTACION, form.respuestas())[1]['valor'] == 'Sí'


@pytest.mark.django_db
def test_aceptacion_es_obligatoria_y_no_se_eligen_estudios_ajenos(catalogo):
    form = _form(ESTUDIOS_Y_ACEPTACION, {'estudios': ['Inactivo de prueba']})
    assert not form.is_valid()
    assert 'autorizo' in form.errors
    assert 'estudios' in form.errors
    # La plantilla genérica le pone asterisco.
    assert form.fields['autorizo'].required
