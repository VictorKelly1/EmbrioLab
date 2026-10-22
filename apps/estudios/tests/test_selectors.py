import datetime
from decimal import Decimal

import pytest

from apps.estudios.models import Estudio
from apps.estudios.selectors import catalogo, referencias_para
from apps.estudios.tests.factories import EstudioFactory, ValorReferenciaFactory
from apps.pacientes.tests.factories import PacienteFactory

pytestmark = pytest.mark.django_db

HOY = datetime.date(2026, 10, 21)


def _claves(estudios):
    return [e.clave for e in estudios]


@pytest.mark.parametrize(
    ('termino', 'claves'),
    [
        ('', ['GLU', 'PLIP', 'ESP']),
        ('LÍPIDOS', ['PLIP']),
        ('espermograma', ['ESP']),
        ('glu', ['GLU']),
        ('nada', []),
    ],
)
def test_catalogo_busca_por_clave_nombre_o_alias(termino, claves):
    assert sorted(_claves(catalogo(termino))) == sorted(claves)


def test_catalogo_oculta_inactivos():
    EstudioFactory(clave='VIEJO', activo=False)
    assert 'VIEJO' not in _claves(catalogo())
    assert 'VIEJO' in _claves(catalogo(incluir_inactivos=True))


@pytest.fixture
def lipidos():
    return Estudio.objects.get(clave='PLIP')


def _paciente(genero='masculino', nacimiento=datetime.date(1990, 6, 1)):
    return PacienteFactory(persona__genero=genero, persona__fecha_nacimiento=nacimiento)


def test_referencia_segun_genero(lipidos):
    hombre = referencias_para(lipidos, _paciente('masculino'), HOY)
    mujer = referencias_para(lipidos, _paciente('femenino'), HOY)
    assert hombre['hdl'].valor_minimo == 40
    assert mujer['hdl'].valor_minimo == 50
    assert hombre['colesterol_total'] == mujer['colesterol_total']


def test_la_de_su_edad_gana_a_la_general(lipidos):
    ValorReferenciaFactory(
        estudio=lipidos,
        clave_campo='colesterol_total',
        valor_minimo=None,
        valor_maximo=170,
        edad_maxima=19,
    )
    joven = _paciente(nacimiento=datetime.date(2010, 1, 1))
    adulto = _paciente()
    assert referencias_para(lipidos, joven, HOY)['colesterol_total'].valor_maximo == 170
    assert referencias_para(lipidos, adulto, HOY)['colesterol_total'].valor_maximo == 200


def test_la_edad_se_calcula_a_la_fecha_y_los_limites_se_incluyen(lipidos):
    ValorReferenciaFactory(
        estudio=lipidos,
        clave_campo='trigliceridos',
        valor_minimo=None,
        valor_maximo=90,
        edad_maxima=17,
    )
    paciente = _paciente(nacimiento=datetime.date(2008, 10, 22))
    # Un día antes de cumplir 18 todavía tiene 17.
    assert referencias_para(lipidos, paciente, HOY)['trigliceridos'].valor_maximo == 90
    siguiente = HOY + datetime.timedelta(days=1)
    assert referencias_para(lipidos, paciente, siguiente)['trigliceridos'].valor_maximo == 150


def test_la_mas_reciente_vigente(lipidos):
    nueva = ValorReferenciaFactory(
        estudio=lipidos,
        clave_campo='ldl',
        valor_minimo=None,
        valor_maximo=Decimal(130),
        vigente_desde=datetime.date(2026, 6, 1),
    )
    ValorReferenciaFactory(
        estudio=lipidos,
        clave_campo='ldl',
        valor_minimo=None,
        valor_maximo=Decimal(110),
        vigente_desde=datetime.date(2027, 1, 1),
    )
    assert referencias_para(lipidos, _paciente(), HOY)['ldl'] == nueva


def test_ignora_las_inactivas(lipidos):
    lipidos.valores_referencia.filter(clave_campo='ldl').update(activo=False)
    assert 'ldl' not in referencias_para(lipidos, _paciente(), HOY)
