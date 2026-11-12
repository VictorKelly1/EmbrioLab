from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.cuentas.tests.factories import AdminFactory, QuimicoFactory, RecepcionistaFactory
from apps.estudios.models import Estudio
from apps.formularios.tests.factories import FormularioLlenadoFactory
from apps.pedidos.models import EstudioPedido
from apps.pedidos.services import completar_estudio, guardar_borrador
from apps.pedidos.tests.factories import EstudioPedidoFactory, PedidoFactory, tomar

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
    return tomar(estudio, quimico)


def _paciente(estudio):
    return estudio.pedido.cita.paciente


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
    # Un estudio que llegó sin pasar por el servicio: sigue en la cola.
    otro = EstudioPedidoFactory(pedido=estudio.pedido, estudio=Estudio.objects.get(clave='GLU'))
    respuesta = cliente_quimico.get(reverse('pedidos:detalle', args=[estudio.pedido_id]))
    contenido = respuesta.content.decode()
    assert _url(estudio) in contenido
    assert _url(otro) not in contenido  # pendiente, en la cola
    # Es su paciente: lo puede volver a tomar (lo que quedó en la cola), soltar o pasar.
    paciente = _paciente(estudio)
    assert reverse('pedidos:paciente_tomar', args=[paciente.pk]) in contenido
    assert reverse('pedidos:paciente_soltar', args=[paciente.pk]) in contenido
    assert reverse('pedidos:paciente_pasar', args=[paciente.pk]) in contenido
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


# Cola de pedidos: se toma al paciente


def test_la_cola_agrupa_por_paciente_y_se_toma_desde_ahi(cliente_quimico, quimico):
    glu = EstudioPedidoFactory()
    paciente = _paciente(glu)
    otro_pedido = PedidoFactory(cita__paciente=paciente)
    plip = EstudioPedidoFactory(pedido=otro_pedido, estudio=Estudio.objects.get(clave='PLIP'))
    ajeno = EstudioPedidoFactory()
    respuesta = cliente_quimico.get(reverse('pedidos:cola'))
    contenido = respuesta.content.decode()
    assert contenido.count(paciente.persona.nombre_completo) == 2  # título y botón
    assert '2 estudios en espera' in contenido
    assert glu.pedido.numero in contenido and otro_pedido.numero in contenido

    tomado = cliente_quimico.post(
        reverse('pedidos:paciente_tomar', args=[paciente.pk]), follow=True
    )
    assert tomado.redirect_chain[-1][0] == reverse('pedidos:cola')
    assert 'quedó a su cargo con 2 estudios' in tomado.content.decode()
    assert [g.paciente for g in tomado.context['pacientes']] == [_paciente(ajeno)]
    for estudio in (glu, plip):
        estudio.refresh_from_db()
        assert estudio.quimico_encargado == quimico


def test_la_cola_vacia(cliente_quimico):
    respuesta = cliente_quimico.get(reverse('pedidos:cola'))
    assert 'No hay pacientes en espera' in respuesta.content.decode()


def test_tomar_un_paciente_ya_tomado_avisa(cliente_quimico):
    estudio = _tomado(QuimicoFactory())
    EstudioPedidoFactory(pedido=estudio.pedido, estudio=Estudio.objects.get(clave='GLU'))
    respuesta = cliente_quimico.post(
        reverse('pedidos:paciente_tomar', args=[_paciente(estudio).pk]), follow=True
    )
    assert respuesta.redirect_chain[-1][0] == reverse('pedidos:cola')
    assert 'ya tiene a este paciente a su cargo' in respuesta.content.decode()


def test_tomar_desde_los_resultados_regresa_ahi(cliente_quimico, quimico):
    estudio = EstudioPedidoFactory()
    paciente = _paciente(estudio)
    respuesta = cliente_quimico.get(_url(estudio))
    assert reverse('pedidos:paciente_tomar', args=[paciente.pk]) in respuesta.content.decode()
    respuesta = cliente_quimico.post(
        reverse('pedidos:paciente_tomar', args=[paciente.pk]), {'siguiente': _url(estudio)}
    )
    assert respuesta.url == _url(estudio)


def test_siguiente_externo_se_ignora(cliente_quimico):
    estudio = EstudioPedidoFactory()
    respuesta = cliente_quimico.post(
        reverse('pedidos:paciente_tomar', args=[_paciente(estudio).pk]),
        {'siguiente': 'https://example.com/'},
    )
    assert respuesta.url == reverse('pedidos:cola')


def test_soltar_y_pasar_desde_el_pedido(cliente_quimico, quimico):
    estudio = _tomado(quimico)
    detalle = reverse('pedidos:detalle', args=[estudio.pedido_id])
    respuesta = cliente_quimico.post(
        reverse('pedidos:paciente_soltar', args=[_paciente(estudio).pk]),
        {'siguiente': detalle},
        follow=True,
    )
    assert respuesta.redirect_chain[-1][0] == detalle
    assert 'regresó a la cola con 1 estudio' in respuesta.content.decode()
    estudio.refresh_from_db()
    assert estudio.quimico_encargado is None

    estudio = _tomado(quimico, 'GLU')
    otro = QuimicoFactory()
    respuesta = cliente_quimico.post(
        reverse('pedidos:paciente_pasar', args=[_paciente(estudio).pk]),
        {'quimico': otro.pk},
        follow=True,
    )
    assert 'quedó a cargo de' in respuesta.content.decode()
    estudio.refresh_from_db()
    assert estudio.quimico_encargado == otro


def test_no_se_pasa_a_si_mismo_desde_el_form(cliente_quimico, quimico):
    estudio = _tomado(quimico)
    respuesta = cliente_quimico.post(
        reverse('pedidos:paciente_pasar', args=[_paciente(estudio).pk]),
        {'quimico': quimico.pk},
        follow=True,
    )
    estudio.refresh_from_db()
    assert estudio.quimico_encargado == quimico
    assert 'Seleccione una opción válida' in respuesta.content.decode()


def test_con_borrador_el_detalle_ya_no_ofrece_soltar(cliente_quimico, quimico):
    estudio = _tomado(quimico)
    guardar_borrador(estudio, {'hdl': Decimal(50)}, quimico=quimico)
    respuesta = cliente_quimico.get(reverse('pedidos:detalle', args=[estudio.pedido_id]))
    contenido = respuesta.content.decode()
    assert reverse('pedidos:paciente_soltar', args=[_paciente(estudio).pk]) not in contenido


def test_la_recepcion_no_suelta_ni_pasa(client, quimico):
    estudio = _tomado(quimico)
    client.force_login(RecepcionistaFactory().usuario)
    paciente = _paciente(estudio)
    assert client.post(reverse('pedidos:paciente_soltar', args=[paciente.pk])).status_code == 403
    assert client.post(reverse('pedidos:paciente_pasar', args=[paciente.pk])).status_code == 403
