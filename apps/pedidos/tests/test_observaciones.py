import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse

from apps.cuentas.tests.factories import QuimicoFactory, RecepcionistaFactory
from apps.pedidos.models import ObservacionPedido
from apps.pedidos.services import agregar_observacion
from apps.pedidos.tests.factories import PedidoFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def pedido():
    return PedidoFactory()


@pytest.fixture
def recepcionista():
    return RecepcionistaFactory()


def _url(pedido):
    return reverse('pedidos:observacion', args=[pedido.pk])


# Servicio


def test_agrega_varias_observaciones_en_orden(pedido, recepcionista):
    agregar_observacion(pedido, '  Enviar todo junto  ', usuario=recepcionista.usuario)
    agregar_observacion(pedido, 'Llamar antes de enviar', usuario=recepcionista.usuario)
    textos = list(pedido.observaciones.values_list('texto', flat=True))
    assert textos == ['Enviar todo junto', 'Llamar antes de enviar']
    assert pedido.observaciones.first().usuario == recepcionista.usuario


@pytest.mark.parametrize('texto', ['', '   ', 'x' * 501])
def test_rechaza_vacia_o_larga(pedido, recepcionista, texto):
    with pytest.raises(ValidationError):
        agregar_observacion(pedido, texto, usuario=recepcionista.usuario)
    assert not ObservacionPedido.objects.exists()


# Vistas


def test_la_recepcion_agrega_y_la_ve_en_el_detalle(client, pedido, recepcionista):
    client.force_login(recepcionista.usuario)
    respuesta = client.post(_url(pedido), {'texto': 'Enviar conforme salgan'})
    assert respuesta.status_code == 302
    detalle = client.get(reverse('pedidos:detalle', args=[pedido.pk]))
    assert 'Enviar conforme salgan' in detalle.text
    assert _url(pedido) in detalle.text


def test_texto_vacio_avisa_sin_guardar(client, pedido, recepcionista):
    client.force_login(recepcionista.usuario)
    respuesta = client.post(_url(pedido), {'texto': ''}, follow=True)
    assert not ObservacionPedido.objects.exists()
    assert 'obligatorio' in respuesta.text


def test_el_quimico_la_ve_pero_no_agrega(client, pedido, recepcionista):
    agregar_observacion(pedido, 'Paciente pide todo junto', usuario=recepcionista.usuario)
    client.force_login(QuimicoFactory().usuario)
    detalle = client.get(reverse('pedidos:detalle', args=[pedido.pk]))
    assert 'Paciente pide todo junto' in detalle.text
    assert _url(pedido) not in detalle.text
    assert client.post(_url(pedido), {'texto': 'otra'}).status_code == 403
    assert ObservacionPedido.objects.count() == 1
