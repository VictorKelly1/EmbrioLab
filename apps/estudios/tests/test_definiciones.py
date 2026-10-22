from decimal import Decimal

import pytest
from django.core.exceptions import ImproperlyConfigured, ValidationError

from apps.estudios.definiciones import REGISTRO, Campo, DefinicionEstudio, obtener
from apps.estudios.definiciones.base import registrar

# PROVISIONAL: casos inventados. Con el Excel del cliente se cambian por sus ejemplos reales.


def _d(**valores):
    return {clave: Decimal(str(valor)) for clave, valor in valores.items()}


def test_las_definiciones_provisionales_estan_registradas():
    assert {'GLU', 'PLIP', 'ESP'} <= REGISTRO.keys()


def test_obtener_clave_inexistente():
    assert obtener('NO-EXISTE') is None


def test_glucosa_solo_captura():
    assert obtener('GLU').resultados(_d(glucosa=92), paciente=None) == {'glucosa': Decimal(92)}


def test_perfil_lipidos_friedewald_e_indice():
    resultados = obtener('PLIP').resultados(
        _d(colesterol_total=200, hdl=50, trigliceridos=150), paciente=None
    )
    assert resultados['ldl'] == Decimal(120)
    assert resultados['indice_aterogenico'] == Decimal('4.0')


def test_perfil_lipidos_redondea_segun_el_campo():
    resultados = obtener('PLIP').resultados(
        _d(colesterol_total=187, hdl=43, trigliceridos=133), paciente=None
    )
    # 187 − 43 − 26.6 = 117.4 → 117; 187 / 43 = 4.348… → 4.3
    assert resultados['ldl'] == Decimal(117)
    assert resultados['indice_aterogenico'] == Decimal('4.3')


def test_perfil_lipidos_sin_ldl_con_trigliceridos_altos():
    resultados = obtener('PLIP').resultados(
        _d(colesterol_total=260, hdl=40, trigliceridos=400), paciente=None
    )
    assert resultados['ldl'] is None
    assert resultados['indice_aterogenico'] == Decimal('6.5')


def test_espermatobioscopia_totales():
    valores = _d(
        volumen='2.5',
        concentracion=40,
        movilidad_progresiva=45,
        movilidad_no_progresiva=15,
        inmoviles=40,
    )
    resultados = obtener('ESP').resultados({**valores, 'aspecto': 'Normal'}, paciente=None)
    assert resultados['total_espermatozoides'] == Decimal('100.0')
    assert resultados['total_moviles_progresivos'] == Decimal('45.0')
    assert resultados['aspecto'] == 'Normal'


def test_espermatobioscopia_la_movilidad_debe_sumar_100():
    valores = _d(
        volumen=3,
        concentracion=20,
        movilidad_progresiva=50,
        movilidad_no_progresiva=20,
        inmoviles=20,
    )
    with pytest.raises(ValidationError, match='sumar 100'):
        obtener('ESP').resultados({**valores, 'aspecto': 'Normal'}, paciente=None)


def test_campo_por_clave_incluye_calculados():
    definicion = obtener('PLIP')
    assert definicion.campo('ldl').formula
    assert definicion.campo('no-existe') is None


def test_json_de_ida_y_vuelta_conserva_los_decimales():
    definicion = obtener('ESP')
    valores = {**_d(volumen='2.5', total_espermatozoides='100.0'), 'aspecto': 'Normal'}
    datos = definicion.a_json({**valores, 'total_moviles_progresivos': None})
    assert datos == {
        'volumen': '2.5',
        'total_espermatozoides': '100.0',
        'aspecto': 'Normal',
        'total_moviles_progresivos': None,
    }
    assert definicion.de_json(datos) == {**valores, 'total_moviles_progresivos': None}


# Registro


def _definicion(**atributos):
    return type('Prueba', (DefinicionEstudio,), atributos)


def test_no_registra_una_clave_repetida():
    with pytest.raises(ImproperlyConfigured, match='Ya hay'):
        registrar(_definicion(clave='GLU', campos=(Campo('x', 'X'),)))


@pytest.mark.parametrize(
    ('atributos', 'mensaje'),
    [
        ({'campos': (Campo('x', 'X'),)}, 'no tiene `clave`'),
        ({'clave': 'T1'}, 'no tiene `campos`'),
        ({'clave': 'T2', 'campos': (Campo('x', 'X'),), 'calculados': (Campo('x', 'Y'),)}, 'repite'),
        ({'clave': 'T3', 'campos': (Campo('x', 'X', tipo='fecha'),)}, 'tipo'),
        ({'clave': 'T4', 'campos': (Campo('x', 'X', tipo='opcion'),)}, 'opciones'),
    ],
)
def test_revisa_la_definicion_al_registrar(atributos, mensaje):
    with pytest.raises(ImproperlyConfigured, match=mensaje):
        registrar(_definicion(**atributos))
    assert REGISTRO.keys() >= {'GLU', 'PLIP', 'ESP'}
    assert not {'T1', 'T2', 'T3', 'T4'} & REGISTRO.keys()
