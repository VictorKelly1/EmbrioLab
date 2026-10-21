import pytest
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ImproperlyConfigured, PermissionDenied
from django.http import HttpResponse
from django.test import RequestFactory
from django.views import View

from apps.core.mixins import RolRequerido
from apps.core.services import dar_de_baja
from apps.cuentas.models import Rol
from apps.cuentas.tests.factories import QuimicoFactory, RecepcionistaFactory

pytestmark = pytest.mark.django_db


class VistaRecepcion(RolRequerido, View):
    roles = [Rol.RECEPCIONISTA]

    def get(self, request):
        return HttpResponse('ok')


class VistaSinRoles(RolRequerido, View):
    def get(self, request):
        return HttpResponse('ok')


def _get(vista, usuario):
    request = RequestFactory().get('/recepcion/')
    request.user = usuario
    return vista.as_view()(request)


def test_permite_al_rol_indicado():
    usuario = RecepcionistaFactory().usuario
    assert _get(VistaRecepcion, usuario).status_code == 200


def test_rechaza_otro_rol():
    usuario = QuimicoFactory().usuario
    with pytest.raises(PermissionDenied):
        _get(VistaRecepcion, usuario)


def test_rechaza_rol_dado_de_baja():
    recepcionista = RecepcionistaFactory()
    dar_de_baja(recepcionista)
    with pytest.raises(PermissionDenied):
        _get(VistaRecepcion, recepcionista.usuario)


def test_anonimo_redirige_al_login():
    respuesta = _get(VistaRecepcion, AnonymousUser())
    assert respuesta.status_code == 302


def test_vista_sin_roles_es_error_de_configuracion():
    with pytest.raises(ImproperlyConfigured):
        _get(VistaSinRoles, RecepcionistaFactory().usuario)
