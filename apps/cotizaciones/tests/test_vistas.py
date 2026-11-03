import pytest
from django.core import mail
from django.urls import reverse

from apps.cuentas.tests.factories import AdminFactory, QuimicoFactory, RecepcionistaFactory
from apps.estudios.models import Estudio
from apps.notificaciones.models import Notificacion
from apps.notificaciones.tests.utils import CORREO, con_contactos
from apps.pacientes.tests.factories import PacienteFactory

pytestmark = pytest.mark.django_db

URL = reverse('cotizaciones:cotizar')


@pytest.fixture
def recepcion(client):
    client.force_login(RecepcionistaFactory().usuario)
    return client


def _ids(*claves):
    return [Estudio.objects.get(clave=c).pk for c in claves]


def test_la_pantalla_lista_el_catalogo(recepcion):
    respuesta = recepcion.get(URL)
    contenido = respuesta.content.decode()
    assert respuesta.status_code == 200
    assert 'Perfil de lípidos' in contenido
    assert 'Todavía no elige estudios' in contenido


@pytest.mark.parametrize('fabrica', [QuimicoFactory, AdminFactory])
def test_solo_la_recepcion(client, fabrica):
    client.force_login(fabrica().usuario)
    assert client.get(URL).status_code == 403


def test_descargar_pdf(recepcion):
    respuesta = recepcion.post(
        URL, {'estudios': _ids('GLU', 'PLIP'), 'cliente': 'Ana', 'accion': 'pdf'}
    )
    assert respuesta['Content-Type'] == 'application/pdf'
    assert respuesta['Content-Disposition'].startswith('attachment; filename="cotizacion-')
    assert respuesta['Cache-Control'] == 'no-store'
    assert respuesta.content.startswith(b'%PDF')


def test_sin_estudios_muestra_el_error(recepcion):
    respuesta = recepcion.post(URL, {'accion': 'pdf'})
    assert respuesta.status_code == 200
    assert 'Elija al menos un estudio' in respuesta.content.decode()


def test_enviar_a_un_correo_escrito_conserva_lo_elegido(recepcion):
    respuesta = recepcion.post(
        URL,
        {'estudios': _ids('GLU'), 'correo': 'ana@example.com', 'accion': 'enviar'},
    )
    contenido = respuesta.content.decode()
    assert 'Cotización enviada a ana@example.com' in contenido
    assert mail.outbox[0].to == ['ana@example.com']
    # Sigue la selección para volver a enviarla o descargarla.
    assert respuesta.context['renglones'][0].clave == 'GLU'
    assert not Notificacion.objects.exists()


def test_enviar_a_un_paciente_registrado_usa_su_nombre_y_contactos(recepcion):
    paciente = PacienteFactory()
    con_contactos(paciente.persona)
    respuesta = recepcion.post(
        URL,
        {'estudios': _ids('ESP'), 'paciente': paciente.pk, 'cliente': 'otro', 'accion': 'enviar'},
    )
    assert mail.outbox[0].to == [CORREO]
    assert f'Hola, {paciente.persona.nombre_completo}' in mail.outbox[0].body
    assert respuesta.context['paciente_elegido'] == paciente


def test_enviar_sin_destino_muestra_el_error(recepcion):
    respuesta = recepcion.post(URL, {'estudios': _ids('GLU'), 'accion': 'enviar'})
    assert 'escriba un correo' in respuesta.content.decode()
    assert mail.outbox == []


def test_correo_invalido(recepcion):
    respuesta = recepcion.post(
        URL, {'estudios': _ids('GLU'), 'correo': 'no-es-correo', 'accion': 'enviar'}
    )
    assert 'Escriba un correo válido' in respuesta.content.decode()
    assert mail.outbox == []


def test_un_estudio_inactivo_no_se_puede_elegir(recepcion):
    glu = Estudio.objects.get(clave='GLU')
    Estudio.objects.filter(pk=glu.pk).update(activo=False)
    respuesta = recepcion.post(URL, {'estudios': [glu.pk], 'accion': 'pdf'})
    assert respuesta.status_code == 200
    assert 'estudios' in respuesta.context['form'].errors
