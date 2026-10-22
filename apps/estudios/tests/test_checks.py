import pytest

from apps.estudios.checks import diferencias, revisar_catalogo
from apps.estudios.tests.factories import EstudioFactory


def _ids(errores):
    return [e.id for e in errores]


def test_sin_diferencias():
    assert diferencias({'A': 1, 'B': 2}, {'A': 1, 'B': 2}) == []


def test_definicion_sin_fila():
    assert _ids(diferencias({'A': 1, 'B': 1}, {'A': 1})) == ['estudios.E001']


def test_fila_sin_definicion():
    assert _ids(diferencias({'A': 1}, {'A': 1, 'Z': 1})) == ['estudios.E002']


def test_version_distinta():
    errores = diferencias({'A': 2}, {'A': 1})
    assert _ids(errores) == ['estudios.E003']
    assert 'versión 1 en la BD y en la 2' in errores[0].msg


@pytest.mark.django_db
def test_el_catalogo_cargado_coincide_con_el_codigo():
    assert revisar_catalogo(databases=['default']) == []


@pytest.mark.django_db
def test_detecta_un_estudio_sin_definicion_en_la_bd():
    EstudioFactory(clave='HUERFANO')
    assert _ids(revisar_catalogo(databases=['default'])) == ['estudios.E002']
