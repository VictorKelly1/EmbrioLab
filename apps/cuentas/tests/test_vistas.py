import pytest
from django.urls import reverse

from apps.cuentas.tests.factories import PASSWORD, RecepcionistaFactory, UsuarioFactory

pytestmark = pytest.mark.django_db

ENTRAR = reverse('cuentas:entrar')
INICIO = reverse('inicio')


def _entrar(client, correo, password=PASSWORD):
    return client.post(ENTRAR, {'username': correo, 'password': password})


def test_pagina_de_login(client):
    respuesta = client.get(ENTRAR)
    assert respuesta.status_code == 200
    assert 'Iniciar sesión' in respuesta.text


def test_login_correcto_lleva_al_inicio(client):
    usuario = RecepcionistaFactory().usuario

    respuesta = _entrar(client, usuario.correo.upper())

    assert respuesta.status_code == 302
    assert respuesta.url == INICIO
    inicio = client.get(INICIO)
    assert inicio.status_code == 200
    assert usuario.persona.nombre in inicio.text
    assert 'Recepcionista' in inicio.text


def test_login_incorrecto_muestra_error(client):
    usuario = RecepcionistaFactory().usuario

    respuesta = _entrar(client, usuario.correo, 'otra-clave')

    assert respuesta.status_code == 200
    assert 'no coinciden' in respuesta.text
    assert '_auth_user_id' not in client.session


def test_inicio_sin_sesion_redirige_al_login(client):
    respuesta = client.get(INICIO)
    assert respuesta.status_code == 302
    assert respuesta.url == f'{ENTRAR}?next={INICIO}'


def test_inicio_sin_rol_es_403(client):
    client.force_login(UsuarioFactory())
    assert client.get(INICIO).status_code == 403


def test_usuario_con_sesion_no_ve_el_login(client):
    client.force_login(RecepcionistaFactory().usuario)
    respuesta = client.get(ENTRAR)
    assert respuesta.status_code == 302


def test_cerrar_sesion(client):
    client.force_login(RecepcionistaFactory().usuario)

    respuesta = client.post(reverse('cuentas:salir'))

    assert respuesta.status_code == 302
    assert respuesta.url == ENTRAR
    assert '_auth_user_id' not in client.session


def test_bloqueo_tras_cinco_intentos_fallidos(client):
    usuario = RecepcionistaFactory().usuario
    for _ in range(5):
        _entrar(client, usuario.correo, 'clave-equivocada')

    respuesta = _entrar(client, usuario.correo)

    assert respuesta.status_code == 429
    assert 'Acceso bloqueado temporalmente' in respuesta.text
    assert '_auth_user_id' not in client.session


def test_bloqueo_no_se_salta_cambiando_mayusculas(client):
    usuario = RecepcionistaFactory().usuario
    for i in range(5):
        correo = usuario.correo.upper() if i % 2 else usuario.correo
        _entrar(client, correo, 'clave-equivocada')

    assert _entrar(client, usuario.correo.title()).status_code == 429


def test_bloqueo_de_una_cuenta_no_afecta_a_otra(client):
    bloqueado = RecepcionistaFactory().usuario
    otro = RecepcionistaFactory().usuario
    for _ in range(5):
        _entrar(client, bloqueado.correo, 'clave-equivocada')

    assert _entrar(client, otro.correo).status_code == 302
