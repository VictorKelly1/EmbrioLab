import datetime

import pytest
from django.test import Client
from django.urls import reverse

from apps.citas.services import TransicionInvalida, generar_token_qr
from apps.citas.tests.factories import CitaFactory
from apps.cuentas.tests.factories import QuimicoFactory, RecepcionistaFactory
from apps.formularios.models import Formulario, FormularioLlenado
from apps.formularios.services import guardar_respuestas
from apps.formularios.tests.factories import VersionFormularioFactory
from apps.pacientes.tests.factories import PacienteFactory

pytestmark = pytest.mark.django_db

ENVIADO = reverse('formulario_enviado')


def _url(token):
    return reverse('formulario_publico', args=[token])


@pytest.fixture
def hombre():
    return PacienteFactory(
        persona__nombre='Raúl', persona__apellido_paterno='Zamora', persona__genero='masculino'
    )


@pytest.fixture
def token(hombre):
    return generar_token_qr(CitaFactory(paciente=hombre))


RESPUESTAS_HOMBRE = {
    'estudio_esperma': 'si',
    'dias_abstinencia': '3',
    'muestra_completa': 'Sí, completa',
    'medicamentos': 'no',
    'enfermedad_reciente': 'no',
}


# Página pública


def test_muestra_el_formulario_de_su_genero_sin_datos_del_paciente(client, hombre, token):
    respuesta = client.get(_url(token))
    assert respuesta.status_code == 200
    assert 'días de abstinencia' in respuesta.text
    assert 'menstruación' not in respuesta.text
    for dato in (hombre.persona.nombre, hombre.persona.apellido_paterno, hombre.folio):
        assert dato not in respuesta.text
    assert hombre.persona.curp not in respuesta.text


def test_encabezados_de_privacidad(client, token):
    respuesta = client.get(_url(token))
    assert respuesta['Cache-Control'] == 'no-store'
    # El link no se manda a otros sitios, pero sí al propio: con 'no-referrer' el
    # navegador envía Origin: null y Django rechaza el POST por CSRF.
    assert respuesta['Referrer-Policy'] == 'same-origin'
    assert 'noindex' in respuesta['X-Robots-Tag']


def test_envio_real_con_csrf_activo(hombre, token):
    navegador = Client(enforce_csrf_checks=True)
    pagina = navegador.get(_url(token))
    csrf = pagina.cookies['csrftoken'].value
    respuesta = navegador.post(
        _url(token),
        {**RESPUESTAS_HOMBRE, 'csrfmiddlewaretoken': csrf},
        headers={'Origin': 'http://testserver'},
    )
    assert respuesta.status_code == 302
    assert FormularioLlenado.objects.exists()


def test_enviar_guarda_y_el_link_ya_no_sirve(client, hombre, token):
    respuesta = client.post(_url(token), RESPUESTAS_HOMBRE)
    assert respuesta.status_code == 302
    assert respuesta.url == ENVIADO

    llenado = FormularioLlenado.objects.get()
    assert llenado.cita.paciente == hombre
    assert llenado.respuestas['dias_abstinencia'] == 3
    assert llenado.respuestas['estudio_esperma'] is True
    assert llenado.version_formulario.formulario.genero_aplicable == 'masculino'

    assert client.get(_url(token)).status_code == 404
    assert client.post(_url(token), RESPUESTAS_HOMBRE).status_code == 404
    assert FormularioLlenado.objects.count() == 1


def test_errores_vuelven_a_mostrar_el_formulario(client, token):
    respuesta = client.post(_url(token), {**RESPUESTAS_HOMBRE, 'dias_abstinencia': ''})
    assert respuesta.status_code == 200
    assert 'dias_abstinencia' in respuesta.context['form'].errors
    assert not FormularioLlenado.objects.exists()


def test_pagina_de_enviado(client):
    assert client.get(ENVIADO).status_code == 200


def test_link_invalido(client):
    respuesta = client.get(_url('no-existe'))
    assert respuesta.status_code == 404
    assert 'ya no está disponible' in respuesta.text


def test_sin_formulario_para_su_genero(client, token):
    Formulario.objects.update(activo=False)
    assert client.get(_url(token)).status_code == 503


# Límite de intentos


def test_bloquea_tras_muchos_links_invalidos(client, settings, token):
    settings.FORMULARIO_LINKS_INVALIDOS_MAX = 3
    for _ in range(3):
        assert client.get(_url('inventado')).status_code == 404
    # Ya bloqueada, ni siquiera un link válido pasa desde esa IP.
    assert client.get(_url('inventado')).status_code == 429
    assert client.get(_url(token)).status_code == 429


def test_bloquea_tras_muchas_peticiones(client, settings, token):
    settings.FORMULARIO_PETICIONES_MAX = 2
    assert client.get(_url(token)).status_code == 200
    assert client.get(_url(token)).status_code == 200
    respuesta = client.get(_url(token))
    assert respuesta.status_code == 429
    assert respuesta['Cache-Control'] == 'no-store'


def test_el_limite_es_por_ip(client, settings, token):
    settings.FORMULARIO_LINKS_INVALIDOS_MAX = 1
    client.get(_url('a'), REMOTE_ADDR='203.0.113.1')
    assert client.get(_url('b'), REMOTE_ADDR='203.0.113.1').status_code == 429
    assert client.get(_url(token), REMOTE_ADDR='203.0.113.2').status_code == 200


# Link de una cita que ya tiene respuestas


def test_no_se_genera_otro_link_si_ya_respondio():
    cita = CitaFactory()
    guardar_respuestas(cita, VersionFormularioFactory(), {})
    with pytest.raises(TransicionInvalida):
        generar_token_qr(cita)


# Recepción


@pytest.fixture
def recepcion(client):
    client.force_login(RecepcionistaFactory().usuario)
    return client


def test_solo_la_recepcionista(client):
    client.force_login(QuimicoFactory().usuario)
    assert client.get(reverse('formularios:lista')).status_code == 403


def test_lista_y_vista_previa(recepcion):
    lista = recepcion.get(reverse('formularios:lista'))
    assert 'Formulario de la visita — hombre' in lista.text

    formulario = Formulario.objects.get(genero_aplicable='femenino')
    detalle = recepcion.get(reverse('formularios:detalle', args=[formulario.pk]))
    assert 'menstruación' in detalle.text
    assert 'Se muestra si responde «Sí»' in detalle.text
    assert all(campo.disabled for campo in detalle.context['vista_previa'].fields.values())


def test_detalle_inexistente(recepcion):
    assert recepcion.get(reverse('formularios:detalle', args=[999])).status_code == 404


def test_la_cita_muestra_las_respuestas(client, recepcion, hombre, token):
    client.post(_url(token), RESPUESTAS_HOMBRE)
    cita = FormularioLlenado.objects.get().cita

    detalle = recepcion.get(reverse('citas:detalle', args=[cita.pk]))
    assert '¿Cuántos días de abstinencia sexual tiene?' in detalle.text
    assert 'Respondido el' in detalle.text
    assert 'Generar un link nuevo' not in detalle.text

    paciente = recepcion.get(reverse('pacientes:detalle', args=[hombre.pk]))
    assert 'Respondido' in paciente.text

    recientes = recepcion.get(reverse('formularios:lista'))
    assert hombre.persona.nombre_completo in recientes.text


def test_fecha_futura_rechazada_en_formulario_de_mujer(client):
    mujer = PacienteFactory(persona__genero='femenino')
    token = generar_token_qr(CitaFactory(paciente=mujer))
    manana = (datetime.date.today() + datetime.timedelta(days=2)).isoformat()
    respuesta = client.post(
        _url(token),
        {
            'fecha_ultima_menstruacion': manana,
            'embarazo': 'No',
            'medicamentos': 'no',
            'enfermedad_reciente': 'no',
        },
    )
    assert respuesta.status_code == 200
    assert 'fecha_ultima_menstruacion' in respuesta.context['form'].errors
