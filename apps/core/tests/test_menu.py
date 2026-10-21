import pytest
from django.urls import reverse

from apps.core.menu import opciones_para
from apps.cuentas.tests.factories import AdminFactory, QuimicoFactory, RecepcionistaFactory

pytestmark = pytest.mark.django_db


def _etiquetas(usuario):
    return [o['etiqueta'] for o in opciones_para(usuario)]


def test_opciones_de_la_recepcionista():
    assert _etiquetas(RecepcionistaFactory().usuario) == [
        'Inicio',
        'Calendario de citas',
        'Pedidos',
        'Pacientes',
        'Formularios',
        'Catálogo de estudios',
        'Doctores',
    ]


def test_opciones_del_quimico():
    assert _etiquetas(QuimicoFactory().usuario) == [
        'Inicio',
        'Pedidos',
        'Pacientes',
        'Catálogo de estudios',
    ]


def test_opciones_del_admin():
    assert _etiquetas(AdminFactory().usuario) == ['Inicio', 'Usuarios', 'Reportes']


def test_las_que_no_existen_aun_no_tienen_url():
    opciones = {o['etiqueta']: o for o in opciones_para(RecepcionistaFactory().usuario)}
    assert opciones['Pacientes']['url'] == reverse('pacientes:lista')
    assert opciones['Calendario de citas']['url'] is None


@pytest.mark.parametrize(
    ('vista', 'activa'),
    [
        ('pacientes:detalle', 'Pacientes'),
        ('pacientes:doctor_editar', 'Doctores'),
        ('inicio', 'Inicio'),
    ],
)
def test_opcion_activa(vista, activa):
    opciones = opciones_para(RecepcionistaFactory().usuario, vista)
    assert [o['etiqueta'] for o in opciones if o['activa']] == [activa]


def test_el_layout_muestra_el_menu_del_rol(client):
    client.force_login(QuimicoFactory().usuario)
    respuesta = client.get(reverse('pacientes:lista'))
    assert 'id="menu-lateral"' in respuesta.text
    assert 'Catálogo de estudios' in respuesta.text
    assert 'Doctores' not in respuesta.text
    assert 'aria-current="page"' in respuesta.text
