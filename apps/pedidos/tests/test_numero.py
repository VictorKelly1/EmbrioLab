import datetime

import pytest

from apps.pedidos.numero import formatear, siguiente_numero

pytestmark = pytest.mark.django_db


def test_consecutivo_por_anio():
    assert siguiente_numero(datetime.date(2026, 3, 1)) == '2026-0001'
    assert siguiente_numero(datetime.date(2026, 12, 31)) == '2026-0002'
    assert siguiente_numero(datetime.date(2027, 1, 1)) == '2027-0001'


def test_formato():
    assert formatear(2026, 7) == '2026-0007'
    assert formatear(2026, 12345) == '2026-12345'
