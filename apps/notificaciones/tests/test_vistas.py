"""Envío del link del formulario desde la cita."""

import pytest
from django.core import mail
from django.urls import reverse

from apps.citas.tests.factories import CitaFactory
from apps.cuentas.tests.factories import QuimicoFactory, RecepcionistaFactory
from apps.notificaciones.models import Notificacion
from apps.notificaciones.tests.utils import con_contactos

pytestmark = pytest.mark.django_db


@pytest.fixture
def recepcion(client):
    client.force_login(RecepcionistaFactory().usuario)
    return client


def _enviar(client, cita):
    return client.post(reverse('citas:enviar_link', args=[cita.pk]))


def test_la_recepcion_envia_el_link(recepcion, django_capture_on_commit_callbacks):
    cita = CitaFactory()
    con_contactos(cita.paciente.persona)
    with django_capture_on_commit_callbacks(execute=True):
        respuesta = _enviar(recepcion, cita)
    assert respuesta.status_code == 302
    assert len(mail.outbox) == 1
    detalle = recepcion.get(respuesta.url).content.decode()
    assert 'El link se enviará por Correo y WhatsApp' in detalle
    assert 'Link del formulario' in detalle  # en el historial de envíos
    assert detalle.count('etiqueta--enviado') == 2


def test_sin_contactos_avisa_y_no_envia(recepcion):
    cita = CitaFactory()
    detalle = recepcion.get(reverse('citas:detalle', args=[cita.pk])).content.decode()
    assert 'agregue un contacto' in detalle
    respuesta = _enviar(recepcion, cita)
    assert 'no tiene correo ni WhatsApp' in recepcion.get(respuesta.url).content.decode()
    assert not Notificacion.objects.exists()


def test_el_boton_dice_por_donde_sale(recepcion):
    cita = CitaFactory()
    con_contactos(cita.paciente.persona, whatsapp='')
    detalle = recepcion.get(reverse('citas:detalle', args=[cita.pk])).content.decode()
    assert 'Enviar link por correo</button>' in detalle


def test_el_quimico_no_envia_links(client):
    cita = CitaFactory()
    con_contactos(cita.paciente.persona)
    client.force_login(QuimicoFactory().usuario)
    assert _enviar(client, cita).status_code == 403


def test_solo_por_post(recepcion):
    assert recepcion.get(reverse('citas:enviar_link', args=[CitaFactory().pk])).status_code == 405
