import pytest

from apps.citas.models import EstadoCita
from apps.citas.selectors import citas_entre, proximas_citas, siguiente_horario_libre
from apps.citas.tests.factories import CitaFactory, en

pytestmark = pytest.mark.django_db


def test_citas_entre():
    dentro = CitaFactory(fecha_hora=en(1, 10))
    CitaFactory(fecha_hora=en(2, 10))
    assert list(citas_entre(en(1, 0), en(2, 0))) == [dentro]


def test_proximas_solo_programadas_y_en_orden():
    segunda = CitaFactory(fecha_hora=en(2, 10))
    primera = CitaFactory(fecha_hora=en(1, 10))
    CitaFactory(fecha_hora=en(1, 12), estado=EstadoCita.ATENDIDA)
    CitaFactory(fecha_hora=en(-1, 10))
    assert list(proximas_citas()) == [primera, segunda]


def test_siguiente_horario_libre():
    CitaFactory(fecha_hora=en(1, 10, 0))
    CitaFactory(fecha_hora=en(1, 10, 30))
    CitaFactory(fecha_hora=en(1, 11, 15))
    # 11:15–11:45 ocupado: se sugiere el siguiente bloque de :00 o :30.
    assert siguiente_horario_libre(en(1, 9, 50)) == en(1, 12, 0)
    assert siguiente_horario_libre(en(1, 9, 10)) == en(1, 9, 30)
    assert siguiente_horario_libre(en(1, 12, 0)) == en(1, 12, 0)
