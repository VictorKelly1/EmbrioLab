import pytest

from apps.personas.models import Persona
from apps.personas.selectors import filtrar_por_nombre
from apps.personas.tests.factories import PersonaFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def personas():
    return {
        'ana': PersonaFactory(nombre='Ana', apellido_paterno='López', apellido_materno='García'),
        'jose': PersonaFactory(
            nombre='José María', apellido_paterno='Núñez', apellido_materno='Ortega'
        ),
        'luis': PersonaFactory(nombre='Luis', apellido_paterno='Pérez', apellido_materno=''),
    }


def _buscar(termino):
    return list(filtrar_por_nombre(Persona.objects.all(), termino))


def test_sin_acentos_ni_mayusculas(personas):
    assert _buscar('NUNEZ') == [personas['jose']]
    assert _buscar('jose maría') == [personas['jose']]


def test_palabras_en_cualquier_orden(personas):
    assert _buscar('garcia ana') == [personas['ana']]


def test_parte_de_una_palabra(personas):
    assert _buscar('lop') == [personas['ana']]


def test_tolera_errores_de_dedo(personas):
    assert personas['ana'] in _buscar('lopes')


def test_sin_coincidencias(personas):
    assert _buscar('Hernández') == []


def test_termino_vacio_no_filtra(personas):
    assert len(_buscar('   ')) == 3


def test_usa_el_indice_trigram(personas):
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute("SELECT indexdef FROM pg_indexes WHERE indexname = 'persona_nombre_trgm'")
        (definicion,) = cursor.fetchone()
    assert 'gin' in definicion and 'gin_trgm_ops' in definicion
