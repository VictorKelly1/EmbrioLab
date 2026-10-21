import pytest

from apps.core.services import dar_de_baja
from apps.pacientes.selectors import buscar_doctores, buscar_pacientes, obtener_paciente
from apps.pacientes.tests.factories import DoctorFactory, PacienteFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def ana():
    return PacienteFactory(
        persona__nombre='Ana',
        persona__apellido_paterno='López',
        persona__apellido_materno='García',
        persona__curp='LOGA920517MJCLRN09',
        numero=15,
    )


@pytest.fixture
def luis():
    return PacienteFactory(
        persona__nombre='Luis',
        persona__apellido_paterno='Pérez',
        persona__curp='PELU800101HDFRRS01',
        numero=16,
    )


def test_sin_termino_mas_recientes_primero(ana, luis):
    assert list(buscar_pacientes()) == [luis, ana]


def test_por_nombre(ana, luis):
    assert list(buscar_pacientes('lopez')) == [ana]


def test_por_curp_o_su_inicio(ana, luis):
    assert list(buscar_pacientes('loga920517mjclrn09')) == [ana]
    assert list(buscar_pacientes('PELU80')) == [luis]


def test_por_numero(ana, luis):
    assert list(buscar_pacientes('16')) == [luis]


def test_inactivos_solo_si_se_piden(ana, luis):
    dar_de_baja(ana)
    assert list(buscar_pacientes('lopez')) == []
    assert list(buscar_pacientes('lopez', incluir_inactivos=True)) == [ana]


def test_lista_sin_consultas_n_mas_1(ana, luis, django_assert_num_queries):
    with django_assert_num_queries(2):  # pacientes + contactos principales
        for paciente in buscar_pacientes():
            list(paciente.persona.contactos.all())


def test_obtener_paciente(ana):
    assert obtener_paciente(ana.pk) == ana


def test_buscar_doctores():
    perez = DoctorFactory(nombre='Dr. Juan Pérez')
    DoctorFactory(nombre='Dra. Laura Gómez')
    assert list(buscar_doctores('juan pér')) == [perez]
