"""Envío de resultados (semana 8): `enviar_resultados` y la pantalla del pedido."""

from decimal import Decimal

import pytest
from django.core import mail
from django.core.exceptions import ValidationError
from django.urls import reverse

from apps.cuentas.tests.factories import QuimicoFactory, RecepcionistaFactory
from apps.notificaciones.models import Notificacion
from apps.notificaciones.tests.utils import CORREO, con_contactos
from apps.pedidos.estados import TransicionInvalida
from apps.pedidos.services import cambiar_estado_pago, enviar_resultados
from apps.pedidos.tests.factories import (
    EstudioPedidoFactory,
    PedidoFactory,
    estudio_completado,
)

pytestmark = pytest.mark.django_db


def _plip():
    return {'colesterol_total': Decimal(210), 'hdl': Decimal(45), 'trigliceridos': Decimal(150)}


@pytest.fixture
def pedido():
    pedido = PedidoFactory()
    con_contactos(pedido.cita.paciente.persona)
    return pedido


@pytest.fixture
def usuario():
    return QuimicoFactory().usuario


# Servicio


def test_registra_quien_envio_y_cuando(pedido, usuario):
    estudio = estudio_completado(pedido=pedido)
    enviar_resultados([estudio], usuario=usuario)
    estudio.refresh_from_db()
    assert estudio.enviado
    assert estudio.usuario_envio == usuario


def test_el_pedido_se_completa_al_enviar_todo(pedido, usuario):
    uno = estudio_completado(pedido=pedido)
    dos = estudio_completado('PLIP', _plip(), pedido=pedido)
    enviar_resultados([uno], usuario=usuario)
    pedido.refresh_from_db()
    assert pedido.estado == 'en_proceso'
    assert pedido.fecha_envio is None
    enviar_resultados([dos], usuario=usuario)
    pedido.refresh_from_db()
    assert pedido.estado == 'completado'
    assert pedido.fecha_envio is not None


def test_no_depende_del_pago(pedido, usuario):
    estudio = estudio_completado(pedido=pedido)
    cambiar_estado_pago(estudio, 'pendiente')
    enviar_resultados([estudio], usuario=usuario)
    pedido.refresh_from_db()
    assert pedido.estado == 'completado'
    assert pedido.estado_pago == 'pendiente'


def test_solo_se_envia_lo_completado(pedido, usuario):
    pendiente = EstudioPedidoFactory(pedido=pedido)
    with pytest.raises(TransicionInvalida, match='Solo se envían estudios completados'):
        enviar_resultados([pendiente], usuario=usuario)
    assert not Notificacion.objects.exists()


def test_los_estudios_deben_ser_de_un_pedido(pedido, usuario):
    otro = PedidoFactory(cita=pedido.cita)
    estudios = [estudio_completado(pedido=pedido), estudio_completado(pedido=otro)]
    with pytest.raises(ValidationError, match='mismo pedido'):
        enviar_resultados(estudios, usuario=usuario)


def test_hace_falta_al_menos_un_estudio(usuario):
    with pytest.raises(ValidationError, match='al menos un estudio'):
        enviar_resultados([], usuario=usuario)


def test_sin_contactos_no_se_marca_como_enviado(usuario):
    estudio = estudio_completado()
    with pytest.raises(ValidationError, match='no tiene correo ni WhatsApp'):
        enviar_resultados([estudio], usuario=usuario)
    estudio.refresh_from_db()
    assert not estudio.enviado


def test_reenviar_conserva_el_primer_envio(pedido, usuario):
    estudio = estudio_completado(pedido=pedido)
    enviar_resultados([estudio], usuario=usuario)
    estudio.refresh_from_db()
    primero = estudio.fecha_envio
    enviar_resultados([estudio], usuario=QuimicoFactory().usuario)
    estudio.refresh_from_db()
    assert estudio.fecha_envio == primero
    assert estudio.usuario_envio == usuario
    assert Notificacion.objects.filter(canal='correo').count() == 2


def test_una_fila_por_estudio_y_canal(pedido, usuario):
    estudios = [
        estudio_completado(pedido=pedido),
        estudio_completado('PLIP', _plip(), pedido=pedido),
    ]
    enviar_resultados(estudios, usuario=usuario)
    assert Notificacion.objects.filter(tipo='resultados').count() == 4


# Pantalla


def _enviar(client, pedido, *estudios):
    return client.post(
        reverse('pedidos:enviar', args=[pedido.pk]), {'estudios': [e.pk for e in estudios]}
    )


def test_el_quimico_envia_desde_el_pedido(
    client, pedido, usuario, django_capture_on_commit_callbacks
):
    estudio = estudio_completado(pedido=pedido)
    client.force_login(usuario)
    with django_capture_on_commit_callbacks(execute=True):
        respuesta = _enviar(client, pedido, estudio)
    assert respuesta.status_code == 302
    assert mail.outbox[0].to == [CORREO]
    detalle = client.get(reverse('pedidos:detalle', args=[pedido.pk])).content.decode()
    assert 'Se enviará 1 estudio al paciente' in detalle
    assert 'Entrega de resultados' in detalle
    assert 'Enviado' in detalle


def test_la_recepcion_no_envia_resultados(client, pedido):
    estudio = estudio_completado(pedido=pedido)
    client.force_login(RecepcionistaFactory().usuario)
    assert _enviar(client, pedido, estudio).status_code == 403
    detalle = client.get(reverse('pedidos:detalle', args=[pedido.pk])).content.decode()
    assert 'Los químicos envían los resultados' in detalle


def test_no_acepta_estudios_sin_completar(client, pedido, usuario):
    pendiente = EstudioPedidoFactory(pedido=pedido)
    estudio_completado(pedido=pedido)
    client.force_login(usuario)
    respuesta = _enviar(client, pedido, pendiente)
    assert respuesta.status_code == 302
    assert not Notificacion.objects.exists()
    detalle = client.get(respuesta.url).content.decode()
    assert 'aviso--error' in detalle


def test_avisa_si_el_paciente_no_tiene_contactos(client, usuario):
    estudio = estudio_completado()
    client.force_login(usuario)
    detalle = client.get(reverse('pedidos:detalle', args=[estudio.pedido_id])).content.decode()
    assert 'no tiene correo ni WhatsApp registrado' in detalle


def test_sin_completados_no_hay_seccion_de_entrega(client, pedido, usuario):
    EstudioPedidoFactory(pedido=pedido)
    client.force_login(usuario)
    detalle = client.get(reverse('pedidos:detalle', args=[pedido.pk])).content.decode()
    assert 'Entrega de resultados' not in detalle
