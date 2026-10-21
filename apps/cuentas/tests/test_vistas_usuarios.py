import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.cuentas.models import Rol, Usuario
from apps.cuentas.tests.factories import AdminFactory, QuimicoFactory, RecepcionistaFactory

pytestmark = pytest.mark.django_db

LISTA = reverse('cuentas:usuarios')
CREAR = reverse('cuentas:usuario_crear')

FORMULARIO = {
    'nombre': 'Rosa',
    'apellido_paterno': 'Quiroz',
    'apellido_materno': '',
    'genero': 'femenino',
    'fecha_nacimiento': '1990-01-01',
    'curp': 'quxr900101mjcrss01',
    'rol': 'quimico',
    'cedula_profesional': '12345678',
    'sueldo': '15000',
    'color': '#7d4aa6',
    'correo': 'Rosa@EmbrioLab.test',
    'password': 'una-clave-segura-987',
    'password_confirmacion': 'una-clave-segura-987',
}


@pytest.fixture
def admin(client):
    client.force_login(AdminFactory().usuario)
    return client


@pytest.mark.parametrize('fabrica', [RecepcionistaFactory, QuimicoFactory])
def test_solo_el_admin(client, fabrica):
    client.force_login(fabrica().usuario)
    assert client.get(LISTA).status_code == 403
    assert client.post(CREAR, FORMULARIO).status_code == 403
    assert not Usuario.objects.filter(correo='rosa@embriolab.test').exists()


def test_lista_de_usuarios(admin):
    RecepcionistaFactory(usuario__persona__nombre='Carmen')
    QuimicoFactory()
    respuesta = admin.get(LISTA)
    assert 'Carmen' in respuesta.text
    assert 'Químico' in respuesta.text


def test_lista_sin_consultas_n_mas_1(admin):
    def consultas():
        with CaptureQueriesContext(connection) as contexto:
            admin.get(LISTA)
        return len(contexto)

    RecepcionistaFactory()
    antes = consultas()
    QuimicoFactory.create_batch(5)
    assert consultas() == antes


def test_registrar_quimico(admin):
    respuesta = admin.post(CREAR, FORMULARIO)

    assert respuesta.status_code == 302
    usuario = Usuario.objects.get(correo='rosa@embriolab.test')
    assert usuario.roles == {Rol.QUIMICO}
    assert usuario.quimico.cedula_profesional == '12345678'
    assert usuario.persona.curp == 'QUXR900101MJCRSS01'
    assert usuario.check_password('una-clave-segura-987')
    assert 'Usuario registrado' in admin.get(LISTA).text


def test_quimico_sin_cedula_error_del_servicio(admin):
    respuesta = admin.post(CREAR, {**FORMULARIO, 'cedula_profesional': ''})
    assert respuesta.status_code == 200
    assert 'cedula_profesional' in respuesta.context['form'].errors
    assert not Usuario.objects.filter(correo='rosa@embriolab.test').exists()


def test_contrasenas_distintas_o_debiles(admin):
    respuesta = admin.post(CREAR, {**FORMULARIO, 'password_confirmacion': 'otra'})
    assert 'password_confirmacion' in respuesta.context['form'].errors

    respuesta = admin.post(
        CREAR, {**FORMULARIO, 'password': '12345678', 'password_confirmacion': '12345678'}
    )
    assert 'password' in respuesta.context['form'].errors
