from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from apps.estudios.models import CategoriaEstudio, Estudio, ValorReferencia
from apps.estudios.tests.factories import ValorReferenciaFactory

pytestmark = pytest.mark.django_db


def test_la_migracion_carga_el_catalogo_provisional():
    assert list(CategoriaEstudio.objects.values_list('nombre', flat=True)) == [
        'Sanguíneos',
        'Esperma',
        'Cultivo',
        'Otros',
    ]
    plip = Estudio.objects.get(clave='PLIP')
    assert plip.definicion.clave == 'PLIP'
    assert plip.alias.filter(alias='perfil lipidico').exists()
    assert plip.valores_referencia.filter(clave_campo='hdl').count() == 2


@pytest.mark.parametrize(
    ('datos', 'texto'),
    [
        ({'valor_minimo': 70, 'valor_maximo': 99}, '70 – 99 mg/dL'),
        ({'valor_minimo': Decimal('1.4'), 'valor_maximo': None}, '≥ 1.4 mg/dL'),
        ({'valor_minimo': None, 'valor_maximo': 200}, '≤ 200 mg/dL'),
        ({'valor_minimo': 0, 'valor_maximo': 5}, '0 – 5 mg/dL'),
        ({'valor_minimo': None, 'valor_maximo': None, 'texto_referencia': 'Negativo'}, 'Negativo'),
    ],
)
def test_rango_legible(datos, texto):
    assert ValorReferenciaFactory.build(**datos).rango == texto


@pytest.mark.parametrize(
    ('datos', 'texto'),
    [
        ({}, 'Todos'),
        ({'genero': 'femenino'}, 'Mujeres'),
        ({'genero': 'masculino', 'edad_minima': 18, 'edad_maxima': 60}, 'Hombres · 18 a 60 años'),
        ({'edad_minima': 65}, '65 años o más'),
        ({'edad_maxima': 12}, 'hasta 12 años'),
    ],
)
def test_a_quien_aplica(datos, texto):
    assert ValorReferenciaFactory.build(**datos).aplica_a == texto


def test_como_json():
    valor = ValorReferenciaFactory()
    assert valor.como_json() == {
        'id': valor.pk,
        'valor_minimo': '70',
        'valor_maximo': '99',
        'texto': '',
        'unidad': 'mg/dL',
        'rango': '70 – 99 mg/dL',
        'vigente_desde': valor.vigente_desde.isoformat(),
    }


@pytest.mark.parametrize(
    ('datos', 'campo'),
    [
        ({'valor_minimo': None, 'valor_maximo': None}, 'texto_referencia'),
        ({'valor_minimo': 100, 'valor_maximo': 50}, 'valor_maximo'),
        ({'edad_minima': 60, 'edad_maxima': 18}, 'edad_maxima'),
    ],
)
def test_clean_rechaza_rangos_invalidos(datos, campo):
    with pytest.raises(ValidationError) as error:
        ValorReferenciaFactory.build(**datos).clean()
    assert campo in error.value.message_dict


@pytest.mark.parametrize(
    'datos',
    [
        {'valor_minimo': None, 'valor_maximo': None},
        {'valor_minimo': 100, 'valor_maximo': 50},
        {'edad_minima': 60, 'edad_maxima': 18},
    ],
)
def test_la_bd_tambien_rechaza_rangos_invalidos(datos):
    with pytest.raises(IntegrityError):
        ValorReferenciaFactory(**datos)


def test_no_existe_valor_sin_estudio():
    assert not ValorReferencia.objects.filter(estudio__isnull=True).exists()
