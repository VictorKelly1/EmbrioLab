import pytest
from django.urls import reverse

from apps.citas.models import EstadoCita
from apps.citas.tests.factories import CitaFactory
from apps.cuentas.tests.factories import AdminFactory, QuimicoFactory, RecepcionistaFactory
from apps.estudios.models import Estudio, EstudioAlias
from apps.pedidos.models import EstudioPedido, Pedido
from apps.pedidos.services import Linea, crear_pedido
from apps.pedidos.tests.factories import PedidoFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def recepcionista():
    return RecepcionistaFactory()


@pytest.fixture
def recepcion(client, recepcionista):
    client.force_login(recepcionista.usuario)
    return client


@pytest.fixture
def quimico(client):
    client.force_login(QuimicoFactory().usuario)
    return client


@pytest.fixture
def cita():
    return CitaFactory(estado=EstadoCita.ATENDIDA)


@pytest.fixture
def catalogo():
    return {e.clave: e for e in Estudio.objects.all()}


@pytest.fixture
def pedido(cita, recepcionista, catalogo):
    return crear_pedido(
        cita=cita,
        recepcionista=recepcionista,
        lineas=[Linea(catalogo['GLU'], 'glucosa'), Linea(catalogo['PLIP'], 'perfil lipidico')],
    )


def _crear_url(cita):
    return f'{reverse("pedidos:crear")}?cita={cita.pk}'


def _linea(i, estudio, nombre='', alias=False, quimicos=()):
    datos = {
        f'form-{i}-nombre_solicitado': nombre,
        f'form-{i}-estudio': estudio.pk,
        f'form-{i}-quimicos': [q.pk for q in quimicos],
    }
    if alias:
        datos[f'form-{i}-guardar_alias'] = 'on'
    return datos


def _formset(*lineas, doctor=''):
    datos = {
        'form-TOTAL_FORMS': len(lineas),
        'form-INITIAL_FORMS': 0,
        'form-MIN_NUM_FORMS': 1,
        'form-MAX_NUM_FORMS': 1000,
        'doctor': doctor,
    }
    for linea in lineas:
        datos.update(linea)
    return datos


# Permisos


def test_sin_sesion(client):
    assert client.get(reverse('pedidos:lista')).status_code == 302


def test_el_admin_no_ve_pedidos(client):
    client.force_login(AdminFactory().usuario)
    assert client.get(reverse('pedidos:lista')).status_code == 403


def test_el_quimico_ve_pero_no_arma_ni_modifica(quimico, cita, pedido):
    assert quimico.get(reverse('pedidos:lista')).status_code == 200
    respuesta = quimico.get(reverse('pedidos:detalle', args=[pedido.pk]))
    assert respuesta.status_code == 200
    assert 'Guardar' not in respuesta.text
    assert quimico.get(_crear_url(cita)).status_code == 403
    estudio = pedido.estudios.first()
    respuesta = quimico.post(
        reverse('pedidos:estudio_actualizar', args=[estudio.pk]),
        {f'fila{estudio.pk}-estado_pago': 'pagado'},
    )
    assert respuesta.status_code == 403


# Armar


def test_pantalla_de_armar(recepcion, cita):
    respuesta = recepcion.get(_crear_url(cita))
    assert respuesta.status_code == 200
    assert cita.paciente.persona.nombre_completo in respuesta.text


@pytest.mark.parametrize('url', ['?cita=999999', '?cita=abc', ''])
def test_armar_sin_cita_valida(recepcion, url):
    assert recepcion.get(reverse('pedidos:crear') + url).status_code == 404


def test_cita_no_atendida_regresa_a_la_cita(recepcion):
    cita = CitaFactory()
    respuesta = recepcion.get(_crear_url(cita))
    assert respuesta.status_code == 302
    assert respuesta.url == reverse('citas:detalle', args=[cita.pk])


def test_armar_pedido(recepcion, recepcionista, cita, catalogo):
    uno, dos = QuimicoFactory(), QuimicoFactory()
    respuesta = recepcion.post(
        _crear_url(cita),
        _formset(
            _linea(0, catalogo['ESP'], 'Seminograma', quimicos=(uno, dos)),
            _linea(1, catalogo['PLIP'], 'Lípidos y más', alias=True),
        ),
    )
    pedido = Pedido.objects.get(cita=cita)
    assert respuesta.status_code == 302
    assert respuesta.url == reverse('pedidos:detalle', args=[pedido.pk])
    assert pedido.recepcionista == recepcionista
    assert pedido.estudios.count() == 2
    esperma = pedido.estudios.get(estudio__clave='ESP')
    assert set(esperma.quimicos_asignados.all()) == {uno, dos}
    assert EstudioAlias.objects.filter(alias='lipidos y mas', estudio=catalogo['PLIP']).exists()


def test_armar_sin_estudio_elegido_muestra_error(recepcion, cita):
    datos = _formset({'form-0-nombre_solicitado': 'algo raro', 'form-0-estudio': ''})
    respuesta = recepcion.post(_crear_url(cita), datos)
    assert respuesta.status_code == 200
    assert not Pedido.objects.exists()


def test_armar_con_error_del_servicio(recepcion, cita, catalogo):
    respuesta = recepcion.post(
        _crear_url(cita), _formset(_linea(0, catalogo['GLU']), _linea(1, catalogo['GLU']))
    )
    assert respuesta.status_code == 200
    assert 'repetido' in respuesta.text


def test_sugerencias(recepcion):
    respuesta = recepcion.get(
        reverse('pedidos:sugerencias'), {'form-3-nombre_solicitado': 'espermograma'}
    )
    assert 'Espermatobioscopia básica' in respuesta.text
    assert 'data-exacta' in respuesta.text
    vacia = recepcion.get(reverse('pedidos:sugerencias'), {'nuevo-nombre_solicitado': 'xyzxyz'})
    assert 'No hay coincidencias' in vacia.text


# Detalle y acciones


def test_lista_y_filtros(recepcion, pedido):
    respuesta = recepcion.get(reverse('pedidos:lista'))
    assert pedido.numero in respuesta.text
    filtrada = recepcion.get(reverse('pedidos:lista'), {'estado_pago': 'pagado'})
    assert pedido.numero not in filtrada.text


def test_la_cita_muestra_sus_pedidos(recepcion, pedido):
    respuesta = recepcion.get(reverse('citas:detalle', args=[pedido.cita.pk]))
    assert pedido.numero in respuesta.text
    assert 'Armar pedido' in respuesta.text


def test_asignar_quimicos_y_pago_desde_la_fila(recepcion, pedido):
    estudio = pedido.estudios.get(estudio__clave='GLU')
    uno, dos = QuimicoFactory(), QuimicoFactory()
    recepcion.post(
        reverse('pedidos:estudio_actualizar', args=[estudio.pk]),
        {
            f'fila{estudio.pk}-quimicos': [uno.pk, dos.pk],
            f'fila{estudio.pk}-estado_pago': 'pagado',
        },
    )
    estudio.refresh_from_db()
    assert (estudio.estado, estudio.estado_pago) == ('en_proceso', 'pagado')
    assert set(estudio.quimicos_asignados.all()) == {uno, dos}
    pedido.refresh_from_db()
    assert (pedido.estado, pedido.estado_pago) == ('en_proceso', 'abonado')


def test_pagar_todo(recepcion, pedido):
    recepcion.post(reverse('pedidos:pago', args=[pedido.pk]), {'estado_pago': 'pagado'})
    pedido.refresh_from_db()
    assert pedido.estado_pago == 'pagado'


def test_agregar_estudio(recepcion, pedido, catalogo):
    respuesta = recepcion.post(
        reverse('pedidos:agregar_estudio', args=[pedido.pk]),
        {'nuevo-nombre_solicitado': '', 'nuevo-estudio': catalogo['ESP'].pk},
    )
    assert respuesta.status_code == 302
    assert pedido.estudios.filter(estudio__clave='ESP').exists()


def test_agregar_repetido_muestra_mensaje(recepcion, pedido, catalogo):
    respuesta = recepcion.post(
        reverse('pedidos:agregar_estudio', args=[pedido.pk]),
        {'nuevo-estudio': catalogo['GLU'].pk},
        follow=True,
    )
    assert 'ya está en el pedido' in respuesta.text


def test_quitar_estudio(recepcion, pedido):
    estudio = pedido.estudios.first()
    recepcion.post(reverse('pedidos:estudio_quitar', args=[estudio.pk]))
    assert not EstudioPedido.objects.filter(pk=estudio.pk).exists()
    ultimo = pedido.estudios.get()
    respuesta = recepcion.post(reverse('pedidos:estudio_quitar', args=[ultimo.pk]), follow=True)
    assert 'al menos un estudio' in respuesta.text


def test_cambiar_doctor(recepcion, pedido):
    from apps.pacientes.tests.factories import DoctorFactory

    doctor = DoctorFactory()
    recepcion.post(reverse('pedidos:doctor', args=[pedido.pk]), {'doctor': doctor.pk})
    pedido.refresh_from_db()
    assert pedido.doctor == doctor


def test_detalle_inexistente(recepcion):
    assert recepcion.get(reverse('pedidos:detalle', args=[999_999])).status_code == 404


def test_pedido_de_otra_fabrica_se_ve(recepcion):
    pedido = PedidoFactory()
    assert recepcion.get(reverse('pedidos:detalle', args=[pedido.pk])).status_code == 200


def test_quitar_a_todos_los_quimicos_muestra_el_error(recepcion, pedido):
    estudio = pedido.estudios.get(estudio__clave='GLU')
    recepcion.post(
        reverse('pedidos:estudio_actualizar', args=[estudio.pk]),
        {
            f'fila{estudio.pk}-quimicos': [QuimicoFactory().pk],
            f'fila{estudio.pk}-estado_pago': 'pendiente',
        },
    )
    respuesta = recepcion.post(
        reverse('pedidos:estudio_actualizar', args=[estudio.pk]),
        {f'fila{estudio.pk}-estado_pago': 'pendiente'},
        follow=True,
    )
    assert 'al menos un químico' in respuesta.text


def test_el_detalle_muestra_casillas_de_quimicos(recepcion, pedido):
    quimico = QuimicoFactory()
    respuesta = recepcion.get(reverse('pedidos:detalle', args=[pedido.pk]))
    estudio = pedido.estudios.first()
    assert f'name="fila{estudio.pk}-quimicos" value="{quimico.pk}"' in respuesta.text
    assert f'form="fila-{estudio.pk}"' in respuesta.text


def test_un_quimico_dado_de_baja_sigue_marcado_en_su_estudio(recepcion, pedido, recepcionista):
    from apps.pedidos.services import asignar_quimicos

    estudio = pedido.estudios.first()
    quimico = QuimicoFactory()
    asignar_quimicos(estudio, [quimico], usuario=recepcionista.usuario)
    quimico.estado_actividad = False
    quimico.save()
    respuesta = recepcion.get(reverse('pedidos:detalle', args=[pedido.pk]))
    assert f'name="fila{estudio.pk}-quimicos" value="{quimico.pk}"' in respuesta.text
    otro = pedido.estudios.last()
    assert f'name="fila{otro.pk}-quimicos" value="{quimico.pk}"' not in respuesta.text
