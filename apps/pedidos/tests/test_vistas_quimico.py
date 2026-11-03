from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.cuentas.tests.factories import AdminFactory, QuimicoFactory, RecepcionistaFactory
from apps.estudios.models import Estudio
from apps.formularios.tests.factories import FormularioLlenadoFactory
from apps.pedidos.models import EstudioPedido
from apps.pedidos.services import completar_estudio, guardar_borrador, tomar_estudio
from apps.pedidos.tests.factories import EstudioPedidoFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def quimico():
    return QuimicoFactory()


@pytest.fixture
def cliente_quimico(client, quimico):
    client.force_login(quimico.usuario)
    return client


def _tomado(quimico, clave='PLIP', **extra):
    estudio = EstudioPedidoFactory(estudio=Estudio.objects.get(clave=clave), **extra)
    tomar_estudio(estudio, quimico=quimico)
    estudio.refresh_from_db()
    return estudio


def _url(estudio):
    return reverse('pedidos:resultados', args=[estudio.pk])


PLIP = {'colesterol_total': '210', 'hdl': '45', 'trigliceridos': '150'}


# Captura


def test_el_form_se_genera_desde_la_definicion_con_referencias(cliente_quimico, quimico):
    respuesta = cliente_quimico.get(_url(_tomado(quimico)))
    assert respuesta.status_code == 200
    form = respuesta.context['form']
    assert list(form.fields) == ['colesterol_total', 'hdl', 'trigliceridos']
    assert form.fields['hdl'].help_text == 'Referencia: ≥ 40 mg/dL'
    assert 'Colesterol LDL' in respuesta.content.decode()  # se calcula al completar


def test_guardar_borrador(cliente_quimico, quimico):
    estudio = _tomado(quimico)
    respuesta = cliente_quimico.post(
        _url(estudio), {'colesterol_total': '210', 'accion': 'borrador'}
    )
    assert respuesta.status_code == 302
    estudio.refresh_from_db()
    assert estudio.estado == 'en_proceso'
    assert estudio.resultados['valores'] == {'colesterol_total': '210'}
    # Al volver, el form trae lo guardado.
    form = cliente_quimico.get(_url(estudio)).context['form']
    assert form.initial == {'colesterol_total': Decimal(210)}


def test_completar(cliente_quimico, quimico):
    estudio = _tomado(quimico)
    respuesta = cliente_quimico.post(_url(estudio), {**PLIP, 'accion': 'completar'})
    assert respuesta.status_code == 302
    assert respuesta.url == reverse('pedidos:detalle', args=[estudio.pedido_id])
    estudio.refresh_from_db()
    assert estudio.estado == 'completado'
    assert estudio.resultados['valores']['ldl'] == '135'


def test_completar_sin_todos_los_campos_muestra_errores(cliente_quimico, quimico):
    estudio = _tomado(quimico)
    respuesta = cliente_quimico.post(
        _url(estudio), {'colesterol_total': '210', 'accion': 'completar'}
    )
    assert respuesta.status_code == 200
    assert set(respuesta.context['form'].errors) == {'hdl', 'trigliceridos'}
    estudio.refresh_from_db()
    assert estudio.estado == 'en_proceso'


def test_los_errores_de_la_definicion_se_muestran(cliente_quimico, quimico):
    estudio = _tomado(quimico, 'ESP')
    datos = {
        'volumen': '2.5',
        'concentracion': '40',
        'movilidad_progresiva': '50',
        'movilidad_no_progresiva': '10',
        'inmoviles': '10',
        'aspecto': 'Normal',
        'accion': 'completar',
    }
    respuesta = cliente_quimico.post(_url(estudio), datos)
    assert respuesta.status_code == 200
    assert 'sumar 100' in respuesta.content.decode()


def test_valida_los_limites_del_campo(cliente_quimico, quimico):
    respuesta = cliente_quimico.post(
        _url(_tomado(quimico)), {**PLIP, 'hdl': '-1', 'accion': 'completar'}
    )
    assert 'hdl' in respuesta.context['form'].errors


def test_completado_se_muestra_con_marcas(cliente_quimico, quimico):
    estudio = _tomado(quimico)
    completar_estudio(
        estudio,
        {k: Decimal(v) for k, v in {**PLIP, 'hdl': '35'}.items()},
        quimico=quimico,
    )
    respuesta = cliente_quimico.get(_url(estudio))
    assert respuesta.context['form'] is None
    contenido = respuesta.content.decode()
    assert 'etiqueta--bajo' in contenido
    assert 'Completar estudio' not in contenido
    # Ya no acepta cambios.
    assert cliente_quimico.post(_url(estudio), {**PLIP, 'accion': 'completar'}).status_code == 403


# Quién puede


def test_un_quimico_que_no_es_el_encargado_solo_ve(client, quimico):
    estudio = _tomado(quimico)
    client.force_login(QuimicoFactory().usuario)
    respuesta = client.get(_url(estudio))
    assert respuesta.status_code == 200
    assert respuesta.context['form'] is None
    assert client.post(_url(estudio), {**PLIP, 'accion': 'completar'}).status_code == 403
    estudio.refresh_from_db()
    assert estudio.estado == 'en_proceso'


def test_la_recepcion_ve_resultados_pero_no_captura(client, quimico):
    estudio = _tomado(quimico)
    guardar_borrador(estudio, {'hdl': Decimal(50)}, quimico=quimico)
    client.force_login(RecepcionistaFactory().usuario)
    respuesta = client.get(_url(estudio))
    assert respuesta.status_code == 200
    assert 'Borrador' in respuesta.content.decode()
    assert client.post(_url(estudio), {**PLIP, 'accion': 'borrador'}).status_code == 403


def test_el_admin_no_entra(client, quimico):
    client.force_login(AdminFactory().usuario)
    assert client.get(_url(_tomado(quimico))).status_code == 403


def test_estudio_inexistente(cliente_quimico):
    assert cliente_quimico.get(reverse('pedidos:resultados', args=[999999])).status_code == 404


# Resultados anteriores


def test_muestra_resultados_anteriores_del_mismo_estudio(cliente_quimico, quimico):
    anterior = _tomado(quimico, 'GLU')
    completar_estudio(anterior, {'glucosa': Decimal(105)}, quimico=quimico)
    actual = _tomado(quimico, 'GLU', pedido__cita__paciente=anterior.pedido.cita.paciente)
    anteriores = cliente_quimico.get(_url(actual)).context['anteriores']
    assert [a.pk for a in anteriores] == [anterior.pk]
    assert anteriores[0].filas[0].marca == 'alto'


# Detalle del pedido, lista e inicio


def test_detalle_del_pedido_para_el_quimico(cliente_quimico, quimico):
    estudio = _tomado(quimico)
    FormularioLlenadoFactory(cita=estudio.pedido.cita)
    otro = EstudioPedidoFactory(pedido=estudio.pedido)
    respuesta = cliente_quimico.get(reverse('pedidos:detalle', args=[estudio.pedido_id]))
    contenido = respuesta.content.decode()
    assert _url(estudio) in contenido
    assert _url(otro) not in contenido  # pendiente, en la cola
    # El otro estudio se puede tomar desde el pedido; el suyo, soltar o pasar.
    assert reverse('pedidos:estudio_tomar', args=[otro.pk]) in contenido
    assert reverse('pedidos:estudio_soltar', args=[estudio.pk]) in contenido
    assert reverse('pedidos:estudio_pasar', args=[estudio.pk]) in contenido
    assert respuesta.context['llenado'] is not None
    assert 'Formulario de la visita' in contenido


def test_filtrar_pedidos_por_quimico(cliente_quimico, quimico):
    mio = _tomado(quimico)
    ajeno = EstudioPedidoFactory()
    lista = reverse('pedidos:lista')
    respuesta = cliente_quimico.get(lista, {'quimico': quimico.pk})
    assert [p.pk for p in respuesta.context['pagina']] == [mio.pedido_id]
    assert respuesta.context['mio'] is None
    sin_filtro = cliente_quimico.get(lista)
    assert {p.pk for p in sin_filtro.context['pagina']} == {mio.pedido_id, ajeno.pedido_id}
    assert sin_filtro.context['mio'] == quimico.pk


def test_filtro_de_fechas_invertidas(cliente_quimico):
    respuesta = cliente_quimico.get(
        reverse('pedidos:lista'), {'desde': '2026-10-10', 'hasta': '2026-10-01'}
    )
    assert 'hasta' in respuesta.context['filtros'].errors


def test_inicio_del_quimico_con_su_lista_de_trabajo(cliente_quimico, quimico):
    estudio = _tomado(quimico)
    _tomado(QuimicoFactory())
    respuesta = cliente_quimico.get(reverse('inicio'))
    assert respuesta.context['trabajo'] == [estudio]
    assert _url(estudio) in respuesta.content.decode()
    assert respuesta.context['en_cola'] == 0


def test_historial_en_la_ficha_del_paciente(cliente_quimico, quimico):
    estudio = _tomado(quimico)
    completar_estudio(estudio, {k: Decimal(v) for k, v in PLIP.items()}, quimico=quimico)
    paciente = estudio.pedido.cita.paciente
    respuesta = cliente_quimico.get(reverse('pacientes:detalle', args=[paciente.pk]))
    assert list(respuesta.context['historial']) == [EstudioPedido.objects.get(pk=estudio.pk)]
    assert _url(estudio) in respuesta.content.decode()
    assert respuesta.context['historial'][0].fecha_completado <= timezone.now()


# Cola de pedidos


def test_la_cola_agrupa_por_pedido_y_se_toma_desde_ahi(cliente_quimico, quimico):
    glu = EstudioPedidoFactory()
    plip = EstudioPedidoFactory(pedido=glu.pedido, estudio=Estudio.objects.get(clave='PLIP'))
    respuesta = cliente_quimico.get(reverse('pedidos:cola'))
    contenido = respuesta.content.decode()
    assert contenido.count(f'Pedido {glu.pedido.numero}') == 1
    assert '2 estudios en espera' in contenido
    tomar = cliente_quimico.post(
        reverse('pedidos:estudio_tomar', args=[glu.pk]), {'volver': 'cola'}, follow=True
    )
    assert tomar.redirect_chain[-1][0] == reverse('pedidos:cola')
    assert 'quedó a su cargo' in tomar.content.decode()
    assert list(tomar.context['estudios']) == [plip]
    glu.refresh_from_db()
    assert glu.quimico_encargado == quimico


def test_la_cola_vacia(cliente_quimico):
    respuesta = cliente_quimico.get(reverse('pedidos:cola'))
    assert 'No hay estudios en espera' in respuesta.content.decode()


def test_tomar_uno_ya_tomado_avisa(cliente_quimico):
    estudio = _tomado(QuimicoFactory())
    respuesta = cliente_quimico.post(
        reverse('pedidos:estudio_tomar', args=[estudio.pk]), follow=True
    )
    assert respuesta.redirect_chain[-1][0] == reverse('pedidos:detalle', args=[estudio.pedido_id])
    assert 'Otro químico ya tomó' in respuesta.content.decode()


def test_tomar_desde_los_resultados(cliente_quimico, quimico):
    estudio = EstudioPedidoFactory()
    respuesta = cliente_quimico.get(_url(estudio))
    assert reverse('pedidos:estudio_tomar', args=[estudio.pk]) in respuesta.content.decode()


def test_soltar_y_pasar_desde_el_pedido(cliente_quimico, quimico):
    estudio = _tomado(quimico)
    respuesta = cliente_quimico.post(
        reverse('pedidos:estudio_soltar', args=[estudio.pk]), follow=True
    )
    assert 'regresó a la cola' in respuesta.content.decode()
    estudio.refresh_from_db()
    assert estudio.quimico_encargado is None

    estudio = _tomado(quimico, 'GLU')
    otro = QuimicoFactory()
    respuesta = cliente_quimico.post(
        reverse('pedidos:estudio_pasar', args=[estudio.pk]),
        {f'pasar{estudio.pk}-quimico': otro.pk},
        follow=True,
    )
    assert 'quedó a cargo de' in respuesta.content.decode()
    estudio.refresh_from_db()
    assert estudio.quimico_encargado == otro


def test_no_se_pasa_a_si_mismo_desde_el_form(cliente_quimico, quimico):
    estudio = _tomado(quimico)
    respuesta = cliente_quimico.post(
        reverse('pedidos:estudio_pasar', args=[estudio.pk]),
        {f'pasar{estudio.pk}-quimico': quimico.pk},
        follow=True,
    )
    estudio.refresh_from_db()
    assert estudio.quimico_encargado == quimico
    assert 'Seleccione una opción válida' in respuesta.content.decode()


def test_con_borrador_el_detalle_ya_no_ofrece_soltar(cliente_quimico, quimico):
    estudio = _tomado(quimico)
    guardar_borrador(estudio, {'hdl': Decimal(50)}, quimico=quimico)
    respuesta = cliente_quimico.get(reverse('pedidos:detalle', args=[estudio.pedido_id]))
    assert reverse('pedidos:estudio_soltar', args=[estudio.pk]) not in respuesta.content.decode()
