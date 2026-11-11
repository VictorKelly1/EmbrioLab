import datetime
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from apps.cotizaciones.cotizacion import CATEGORIA_LIBRE, EstudioLibre, cotizar
from apps.estudios.models import Estudio

pytestmark = pytest.mark.django_db


@pytest.fixture
def catalogo():
    return {e.clave: e for e in Estudio.objects.select_related('categoria')}


def test_cotizar_suma_los_precios_vigentes(catalogo):
    cotizacion = cotizar(
        [catalogo['GLU'], catalogo['ESP']],
        cliente='  Ana   López ',
        fecha=datetime.date(2026, 11, 3),
    )
    assert cotizacion.cliente == 'Ana López'
    assert [r.clave for r in cotizacion.renglones] == ['GLU', 'ESP']
    assert cotizacion.renglones[0].precio == catalogo['GLU'].precio
    assert cotizacion.renglones[1].categoria == str(catalogo['ESP'].categoria)
    assert cotizacion.total == catalogo['GLU'].precio + catalogo['ESP'].precio
    assert cotizacion.fecha == datetime.date(2026, 11, 3)


def test_usa_el_precio_del_momento(catalogo):
    glu = catalogo['GLU']
    glu.precio = Decimal('99.50')
    assert cotizar([glu]).total == Decimal('99.50')


def test_cotizar_no_guarda_nada(catalogo, django_assert_num_queries):
    with django_assert_num_queries(0):
        cotizar([catalogo['GLU']])


def test_sin_estudios():
    with pytest.raises(ValidationError, match='al menos un estudio'):
        cotizar([])


def test_estudio_repetido(catalogo):
    with pytest.raises(ValidationError, match='repetido'):
        cotizar([catalogo['GLU'], catalogo['GLU']])


def test_estudio_inactivo(catalogo):
    glu = catalogo['GLU']
    glu.activo = False
    with pytest.raises(ValidationError, match='Glucosa'):
        cotizar([glu, catalogo['PLIP']])


# Estudios libres (no están en el catálogo)


def test_estudios_libres_van_despues_con_su_precio(catalogo):
    cotizacion = cotizar(
        [catalogo['GLU']],
        libres=[
            EstudioLibre('  Prueba   de VIH ', Decimal('350.00'), 'Sanguíneos'),
            EstudioLibre('Cultivo especial', Decimal('0')),
        ],
    )
    assert [r.nombre for r in cotizacion.renglones] == [
        catalogo['GLU'].nombre,
        'Prueba de VIH',
        'Cultivo especial',
    ]
    assert cotizacion.renglones[1].clave == ''
    assert cotizacion.renglones[1].categoria == 'Sanguíneos'
    assert cotizacion.renglones[2].categoria == CATEGORIA_LIBRE
    assert cotizacion.total == catalogo['GLU'].precio + Decimal('350.00')


def test_solo_con_estudios_libres():
    cotizacion = cotizar(libres=[EstudioLibre('Prueba X', Decimal('100'))])
    assert cotizacion.total == Decimal('100')


@pytest.mark.parametrize(
    ('libre', 'mensaje'),
    [
        (EstudioLibre('   ', Decimal('10')), 'nombre'),
        (EstudioLibre('Prueba X', Decimal('-1')), 'precio'),
    ],
)
def test_estudio_libre_invalido(libre, mensaje):
    with pytest.raises(ValidationError, match=mensaje):
        cotizar(libres=[libre])
