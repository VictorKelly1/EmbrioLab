"""
Matriz de permisos: quién puede entrar a cada URL del sistema (CONTEXTO.md §2 y §5).

Es la especificación de los permisos. Si agrega una URL, agréguela aquí: la prueba falla
mientras haya una URL fuera de la matriz, para que ninguna vista quede abierta sin revisar.
"""

import pytest
from django.conf import settings
from django.urls import URLPattern, URLResolver, get_resolver, reverse

from apps.cuentas.models import Rol
from apps.cuentas.tests.factories import AdminFactory, QuimicoFactory, RecepcionistaFactory

pytestmark = pytest.mark.django_db

ADMIN, RECEPCION, QUIMICO = Rol.ADMIN, Rol.RECEPCIONISTA, Rol.QUIMICO
PERSONAL = {ADMIN, RECEPCION, QUIMICO}

MATRIZ = {
    'inicio': PERSONAL,
    # Cuentas
    'cuentas:usuarios': {ADMIN},
    'cuentas:usuario_crear': {ADMIN},
    # Citas: el químico ve el calendario y el detalle, sin cambiar nada.
    'citas:calendario': {RECEPCION, QUIMICO},
    'citas:detalle': {RECEPCION, QUIMICO},
    'citas:agendar': {RECEPCION},
    'citas:espontanea': {RECEPCION},
    'citas:buscar_paciente': {RECEPCION},
    'citas:reprogramar': {RECEPCION},
    'citas:accion': {RECEPCION},
    'citas:llegada': {RECEPCION},
    'citas:generar_qr': {RECEPCION},
    'citas:enviar_link': {RECEPCION},
    # Cotizaciones
    'cotizaciones:cotizar': {RECEPCION},
    # Documentos
    'documentos:resultados': {RECEPCION, QUIMICO},
    # Catálogo: alias la recepción, valores de referencia el químico.
    'estudios:lista': {RECEPCION, QUIMICO},
    'estudios:detalle': {RECEPCION, QUIMICO},
    'estudios:alias_crear': {RECEPCION},
    'estudios:alias_editar': {RECEPCION},
    'estudios:alias_eliminar': {RECEPCION},
    'estudios:referencia_crear': {QUIMICO},
    'estudios:referencia_editar': {QUIMICO},
    'estudios:referencia_activo': {QUIMICO},
    # Formularios llenados
    'formularios:lista': {RECEPCION},
    'formularios:detalle': {RECEPCION},
    # Pacientes y doctores
    'pacientes:lista': {RECEPCION, QUIMICO},
    'pacientes:detalle': {RECEPCION, QUIMICO},
    'pacientes:crear': {RECEPCION},
    'pacientes:editar': {RECEPCION},
    'pacientes:baja': {RECEPCION},
    'pacientes:doctores': {RECEPCION, QUIMICO},
    'pacientes:doctor_crear': {RECEPCION, QUIMICO},
    'pacientes:doctor_editar': {RECEPCION, QUIMICO},
    # Pedidos: la recepción los arma; el químico toma pacientes, captura y envía.
    'pedidos:lista': {RECEPCION, QUIMICO},
    'pedidos:detalle': {RECEPCION, QUIMICO},
    'pedidos:resultados': {RECEPCION, QUIMICO},
    'pedidos:crear': {RECEPCION},
    'pedidos:sugerencias': {RECEPCION},
    'pedidos:doctor': {RECEPCION},
    'pedidos:observacion': {RECEPCION},
    'pedidos:pago': {RECEPCION},
    'pedidos:agregar_estudio': {RECEPCION},
    'pedidos:estudio_actualizar': {RECEPCION},
    'pedidos:estudio_quitar': {RECEPCION},
    'pedidos:cola': {QUIMICO},
    'pedidos:enviar': {QUIMICO},
    'pedidos:paciente_tomar': {QUIMICO},
    'pedidos:paciente_soltar': {QUIMICO},
    'pedidos:paciente_pasar': {QUIMICO},
    # Fotos: cada quien ve la de las personas que su rol le deja ver.
    'personas:foto': PERSONAL,
}

# Sin sesión, a propósito.
PUBLICAS = {
    'cuentas:entrar',
    'cuentas:salir',
    'formulario_publico',  # el link/QR del paciente (token, rate limit)
    'formulario_enviado',
}

FABRICAS = {ADMIN: AdminFactory, RECEPCION: RecepcionistaFactory, QUIMICO: QuimicoFactory}

# Un id que no existe: quien no tiene permiso debe recibir 403 igual, sin que se note si
# el objeto existe (los objetos se cargan después de revisar el rol).
NO_EXISTE = 999_999


def _patrones(patrones, namespace=None):
    for patron in patrones:
        if isinstance(patron, URLResolver):
            if patron.app_name == 'admin':
                continue
            yield from _patrones(patron.url_patterns, patron.namespace or namespace)
        elif isinstance(patron, URLPattern) and patron.name:
            nombre = f'{namespace}:{patron.name}' if namespace else patron.name
            yield nombre, patron


PATRONES = dict(_patrones(get_resolver().url_patterns))


def _url(nombre):
    argumentos = PATRONES[nombre].pattern.converters
    if 'token' in argumentos:
        return reverse(nombre, args=['x'])
    return reverse(nombre, args=[NO_EXISTE] if argumentos else [])


def _pedir(client, nombre):
    """GET si la vista lo acepta; si no, POST (las acciones solo aceptan POST)."""
    vista = PATRONES[nombre].callback.view_class
    metodo = client.get if 'get' in vista.http_method_names else client.post
    return metodo(_url(nombre))


def test_toda_url_esta_en_la_matriz():
    assert set(PATRONES) == set(MATRIZ) | PUBLICAS


@pytest.mark.parametrize('nombre', sorted(MATRIZ))
def test_la_vista_declara_los_roles_de_la_matriz(nombre):
    vista = PATRONES[nombre].callback.view_class
    assert set(vista.roles) == MATRIZ[nombre]


@pytest.mark.parametrize('nombre', sorted(MATRIZ))
def test_sin_sesion_va_al_login(client, nombre):
    respuesta = _pedir(client, nombre)
    assert respuesta.status_code == 302
    assert respuesta.url.startswith(reverse(settings.LOGIN_URL))


CASOS = [(nombre, rol) for nombre in sorted(MATRIZ) for rol in sorted(PERSONAL)]


@pytest.mark.parametrize(('nombre', 'rol'), CASOS)
def test_cada_rol_entra_solo_a_lo_suyo(client, nombre, rol):
    client.force_login(FABRICAS[rol]().usuario)
    respuesta = _pedir(client, nombre)
    if rol in MATRIZ[nombre]:
        assert respuesta.status_code != 403
    else:
        assert respuesta.status_code == 403


@pytest.mark.parametrize('rol', sorted(PERSONAL - {ADMIN}))
def test_el_admin_de_django_es_solo_del_admin(client, rol):
    client.force_login(FABRICAS[rol]().usuario)
    respuesta = client.get(reverse('admin:index'))
    assert respuesta.status_code == 302
    assert respuesta.url.startswith(reverse('admin:login'))
