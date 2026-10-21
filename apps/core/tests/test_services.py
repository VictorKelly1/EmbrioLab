import pytest

from apps.core.models import BorradoFisicoNoPermitido
from apps.core.services import dar_de_baja, reactivar
from apps.cuentas.models import Recepcionista
from apps.cuentas.tests.factories import RecepcionistaFactory

pytestmark = pytest.mark.django_db


def test_dar_de_baja_y_reactivar():
    recepcionista = RecepcionistaFactory()

    dar_de_baja(recepcionista)
    recepcionista.refresh_from_db()
    assert recepcionista.estado_actividad is False
    assert recepcionista not in Recepcionista.objects.activos()
    assert recepcionista in Recepcionista.objects.inactivos()

    reactivar(recepcionista)
    recepcionista.refresh_from_db()
    assert recepcionista.estado_actividad is True


def test_no_se_permite_borrado_fisico():
    recepcionista = RecepcionistaFactory()

    with pytest.raises(BorradoFisicoNoPermitido):
        recepcionista.delete()
    with pytest.raises(BorradoFisicoNoPermitido):
        Recepcionista.objects.all().delete()
    assert Recepcionista.objects.filter(pk=recepcionista.pk).exists()
