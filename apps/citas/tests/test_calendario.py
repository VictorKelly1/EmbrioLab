import datetime

import pytest

from apps.citas.calendario import Vista, armar_filas, dias_de, rango
from apps.citas.tests.factories import CitaFactory, en

pytestmark = pytest.mark.django_db

MIERCOLES = datetime.date(2026, 10, 21)


@pytest.fixture(autouse=True)
def horario(settings):
    settings.CITAS_HORA_INICIO = '08:00'
    settings.CITAS_HORA_FIN = '20:00'
    settings.CITAS_DIAS_HABILES = [0, 1, 2, 3, 4, 5]


def test_semana_de_lunes_a_sabado():
    dias = dias_de(MIERCOLES, Vista.SEMANA)
    assert dias[0] == datetime.date(2026, 10, 19)
    assert dias[-1] == datetime.date(2026, 10, 24)
    assert len(dias) == 6


def test_domingo_aparece_si_es_el_dia_elegido():
    domingo = datetime.date(2026, 10, 25)
    assert domingo in dias_de(domingo, Vista.SEMANA)


def test_dia_no_habil_con_citas_aparece():
    domingo = datetime.date(2026, 10, 25)
    assert domingo in dias_de(MIERCOLES, Vista.SEMANA, {domingo})
    assert domingo not in dias_de(MIERCOLES, Vista.SEMANA)


def test_vista_dia():
    assert dias_de(MIERCOLES, Vista.DIA) == [MIERCOLES]


def test_bloques_de_30_minutos_en_el_horario():
    filas = armar_filas([MIERCOLES], [])
    assert filas[0].hora == datetime.time(8, 0)
    assert filas[-1].hora == datetime.time(19, 30)
    assert len(filas) == 24


def test_cada_cita_en_su_bloque():
    cita = CitaFactory(fecha_hora=en(1, 10, 15))
    dia = cita.fecha_hora.date()
    filas = armar_filas([dia], [cita])
    fila = next(f for f in filas if f.hora == datetime.time(10, 0))
    assert fila.celdas[0].citas == [cita]


def test_el_horario_se_extiende_para_citas_fuera_de_el():
    cita = CitaFactory(fecha_hora=en(1, 21, 0))
    filas = armar_filas([cita.fecha_hora.date()], [cita])
    assert filas[-1].hora == datetime.time(21, 0)


def test_rango_cubre_los_dias_completos():
    inicio, fin = rango(dias_de(MIERCOLES, Vista.SEMANA))
    assert fin - inicio == datetime.timedelta(days=6)
