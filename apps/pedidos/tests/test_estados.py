from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from apps.pedidos.estados import (
    TransicionInvalida,
    estado_del_pedido,
    pago_del_pedido,
    total_del_pedido,
    validar_transicion,
)

ENVIADO = datetime(2026, 10, 21)


def _e(estado='pendiente', pago='pendiente', enviado=False, precio=100):
    return SimpleNamespace(estado=estado, estado_pago=pago, enviado=enviado, precio=Decimal(precio))


@pytest.mark.parametrize(
    ('actual', 'nuevo'), [('pendiente', 'en_proceso'), ('en_proceso', 'completado')]
)
def test_transiciones_validas(actual, nuevo):
    validar_transicion(actual, nuevo)


@pytest.mark.parametrize(
    ('actual', 'nuevo'),
    [
        ('pendiente', 'completado'),
        ('en_proceso', 'pendiente'),
        ('completado', 'en_proceso'),
        ('completado', 'pendiente'),
    ],
)
def test_transiciones_invalidas(actual, nuevo):
    with pytest.raises(TransicionInvalida):
        validar_transicion(actual, nuevo)


@pytest.mark.parametrize(
    ('estudios', 'esperado'),
    [
        ([_e(), _e()], 'pendiente'),
        ([_e(), _e('en_proceso')], 'en_proceso'),
        ([_e('completado', enviado=True), _e('en_proceso')], 'en_proceso'),
        # Completado pero sin enviar: el pedido sigue en proceso.
        ([_e('completado'), _e('completado', enviado=True)], 'en_proceso'),
        # Enviado sin pagar: ya está completado (el envío no depende del pago).
        ([_e('completado', enviado=True), _e('completado', enviado=True)], 'completado'),
    ],
)
def test_estado_del_pedido(estudios, esperado):
    assert estado_del_pedido(estudios) == esperado


@pytest.mark.parametrize(
    ('pagos', 'esperado'),
    [
        (['pagado', 'pagado'], 'pagado'),
        (['pendiente', 'pendiente'], 'pendiente'),
        (['pagado', 'pendiente'], 'abonado'),
        (['abonado'], 'abonado'),
        ([], 'pendiente'),
    ],
)
def test_pago_del_pedido(pagos, esperado):
    assert pago_del_pedido([_e(pago=p) for p in pagos]) == esperado


def test_total_del_pedido():
    assert total_del_pedido([_e(precio=120), _e(precio='450.50')]) == Decimal('570.50')
    assert total_del_pedido([]) == 0
