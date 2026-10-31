"""El worker: arma los mensajes, envía por cada canal, marca y reintenta."""

import datetime
import re
from decimal import Decimal
from unittest import mock

import pytest
from django.core import mail

from apps.citas.services import obtener_cita_por_token
from apps.citas.tests.factories import CitaFactory
from apps.formularios.tests.factories import FormularioLlenadoFactory
from apps.notificaciones import envio
from apps.notificaciones.canales import CanalCorreo, CanalWhatsApp
from apps.notificaciones.models import Notificacion
from apps.notificaciones.services import enviar_link_formulario, notificar_resultados
from apps.notificaciones.tasks import encolar, enviar_notificaciones
from apps.notificaciones.tests.utils import WHATSAPP, con_contactos
from apps.pedidos.tests.factories import PedidoFactory, estudio_completado

pytestmark = pytest.mark.django_db


@pytest.fixture
def whatsapp():
    """Los mensajes que «sale» el stub de WhatsApp."""
    enviados = []
    with mock.patch.object(CanalWhatsApp, 'enviar', autospec=True) as enviar:
        enviar.side_effect = lambda canal, mensaje: enviados.append(mensaje)
        yield enviados


@pytest.fixture
def reintentos(settings):
    settings.NOTIFICACIONES_REINTENTOS = [1, 5]


def _cita():
    cita = CitaFactory()
    con_contactos(cita.paciente.persona)
    return cita


def _token(texto: str) -> str:
    return re.search(r'/f/([\w-]+)/', texto).group(1)


def _estados():
    return dict(Notificacion.objects.values_list('canal', 'estado'))


# Link del formulario


def test_correo_y_whatsapp_llevan_el_mismo_link(whatsapp):
    filas = enviar_link_formulario(_cita())
    envio.procesar([f.pk for f in filas])
    assert _token(mail.outbox[0].body) == _token(whatsapp[0].texto)
    assert whatsapp[0].destinatario == WHATSAPP


def test_el_stub_de_whatsapp_cuenta_como_enviado(caplog):
    filas = enviar_link_formulario(_cita())
    with caplog.at_level('INFO', logger='apps.notificaciones'):
        envio.procesar([f.pk for f in filas])
    assert _estados() == {'correo': 'enviado', 'whatsapp': 'enviado'}
    assert f'WhatsApp (sin integrar) a {WHATSAPP}' in caplog.text


def test_un_canal_que_falla_queda_fallido_con_el_error(whatsapp):
    filas = enviar_link_formulario(_cita())
    with mock.patch.object(CanalCorreo, 'enviar', side_effect=OSError('SMTP caído')):
        reintentar = envio.procesar([f.pk for f in filas])
    assert _estados() == {'correo': 'fallido', 'whatsapp': 'enviado'}
    assert Notificacion.objects.get(canal='correo').error == 'OSError: SMTP caído'
    # Hay un link nuevo en cada intento: se reintenta en todos los canales.
    assert sorted(reintentar) == sorted(f.pk for f in filas)


def test_al_reintentar_el_link_anterior_deja_de_servir(whatsapp):
    cita = _cita()
    ids = [f.pk for f in enviar_link_formulario(cita)]
    with mock.patch.object(CanalCorreo, 'enviar', side_effect=OSError('SMTP caído')):
        envio.procesar(ids)
    primero = _token(whatsapp[0].texto)
    envio.procesar(ids)
    assert _estados() == {'correo': 'enviado', 'whatsapp': 'enviado'}
    assert _token(mail.outbox[0].body) == _token(whatsapp[1].texto) != primero
    assert obtener_cita_por_token(_token(mail.outbox[0].body)) == cita


def test_si_ya_lleno_el_formulario_falla_sin_reintentar(whatsapp):
    cita = _cita()
    ids = [f.pk for f in enviar_link_formulario(cita)]
    FormularioLlenadoFactory(cita=cita)
    assert envio.procesar(ids) == []
    assert _estados() == {'correo': 'fallido', 'whatsapp': 'fallido'}
    assert 'ya llenó el formulario' in Notificacion.objects.first().error


def test_si_la_cita_se_cancelo_falla_sin_reintentar(whatsapp):
    cita = _cita()
    ids = [f.pk for f in enviar_link_formulario(cita)]
    cita.delete()
    assert envio.procesar(ids) == []
    assert Notificacion.objects.filter(estado='fallido').count() == 2


# Reintentos de la tarea


def test_la_tarea_reintenta_hasta_que_sale(reintentos, whatsapp):
    ids = [f.pk for f in enviar_link_formulario(_cita())]
    fallas = [OSError('uno'), None]
    with mock.patch.object(CanalCorreo, 'enviar', side_effect=fallas) as correo:
        enviar_notificaciones.enqueue(ids)
    assert correo.call_count == 2
    assert _estados() == {'correo': 'enviado', 'whatsapp': 'enviado'}


def test_la_tarea_se_rinde_tras_los_reintentos(reintentos, whatsapp):
    ids = [f.pk for f in enviar_link_formulario(_cita())]
    with mock.patch.object(CanalCorreo, 'enviar', side_effect=OSError('SMTP caído')) as correo:
        enviar_notificaciones.enqueue(ids)
    assert correo.call_count == 3  # el intento y los 2 reintentos
    assert _estados()['correo'] == 'fallido'


def test_con_worker_el_reintento_espera(reintentos, settings):
    settings.TASKS = {'default': {'BACKEND': 'django.tasks.backends.dummy.DummyBackend'}}
    resultado = encolar([1], intento=2, espera=datetime.timedelta(minutes=5))
    assert resultado.task.run_after is not None
    assert resultado.args == [[1]]
    assert resultado.kwargs == {'intento': 2}


# Resultados


def _resultados():
    pedido = PedidoFactory()
    con_contactos(pedido.cita.paciente.persona)
    plip = {'colesterol_total': Decimal(210), 'hdl': Decimal(45), 'trigliceridos': Decimal(150)}
    return [
        estudio_completado('GLU', pedido=pedido),
        estudio_completado('PLIP', plip, pedido=pedido),
    ]


def test_un_solo_correo_con_un_pdf_para_varios_estudios(whatsapp):
    estudios = _resultados()
    filas = notificar_resultados(estudios)
    envio.procesar([f.pk for f in filas])
    assert len(mail.outbox) == 1
    correo = mail.outbox[0]
    assert correo.subject == 'Sus resultados de EmbrioLab'
    assert 'Glucosa en ayuno' in correo.body
    assert 'Perfil de lípidos' in correo.body
    ((nombre, contenido, tipo),) = correo.attachments
    assert nombre == f'resultados-{estudios[0].pedido.numero.lower()}.pdf'
    assert tipo == 'application/pdf'
    assert contenido.startswith(b'%PDF')
    assert len(whatsapp) == 1
    assert len(whatsapp[0].adjuntos) == 1
    assert set(Notificacion.objects.values_list('estado', flat=True)) == {'enviado'}


def test_si_el_correo_falla_fallan_todas_sus_filas(whatsapp):
    estudios = _resultados()
    filas = notificar_resultados(estudios)
    with mock.patch.object(CanalCorreo, 'enviar', side_effect=OSError('SMTP caído')):
        reintentar = envio.procesar([f.pk for f in filas])
    correo = Notificacion.objects.filter(canal='correo')
    assert set(correo.values_list('estado', 'error')) == {('fallido', 'OSError: SMTP caído')}
    assert sorted(reintentar) == sorted(correo.values_list('pk', flat=True))
    assert set(Notificacion.objects.filter(canal='whatsapp').values_list('estado', flat=True)) == {
        'enviado'
    }
