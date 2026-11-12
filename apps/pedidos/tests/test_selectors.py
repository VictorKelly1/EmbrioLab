import datetime

import pytest
from django.utils import timezone

from apps.citas.models import EstadoCita
from apps.cuentas.tests.factories import QuimicoFactory
from apps.estudios.models import Estudio
from apps.estudios.selectors import sugerir_estudios
from apps.pedidos.models import Pedido
from apps.pedidos.selectors import (
    buscar_pedidos,
    cola_de_estudios,
    cola_por_paciente,
    historial_de_paciente,
    lista_de_trabajo,
    quimicos_activos,
)
from apps.pedidos.tests.factories import EstudioPedidoFactory, PedidoFactory, tomar

pytestmark = pytest.mark.django_db


def _claves(sugerencias):
    return [s.estudio.clave for s in sugerencias]


def test_sugerencia_exacta_por_alias():
    primera = sugerir_estudios('Espermograma')[0]
    assert (primera.estudio.clave, primera.exacta, primera.coincide_con) == (
        'ESP',
        True,
        'espermograma',
    )


@pytest.mark.parametrize(
    ('texto', 'clave'),
    [
        ('perfil lipidico completo', 'PLIP'),  # contiene un alias
        ('glucoza', 'GLU'),  # error de dedo
        ('Perfil de Lípidos', 'PLIP'),  # el nombre con acentos
        ('esp', 'ESP'),  # la clave
    ],
)
def test_sugerencias_parecidas(texto, clave):
    assert sugerir_estudios(texto)[0].estudio.clave == clave


def test_sin_sugerencias():
    assert sugerir_estudios('tomografia') == []
    assert sugerir_estudios('g') == []


def test_buscar_pedidos_por_numero_folio_y_paciente():
    pedido = PedidoFactory(
        numero='2026-0042',
        cita__paciente__persona__nombre='Begoña',
        cita__paciente__persona__apellido_paterno='Ruiz',
    )
    EstudioPedidoFactory(pedido=pedido)
    otro = PedidoFactory()
    assert list(buscar_pedidos('0042')) == [pedido]
    assert list(buscar_pedidos(pedido.cita.numero_folio.lower())) == [pedido]
    assert list(buscar_pedidos('begona')) == [pedido]
    assert buscar_pedidos('0042')[0].num_estudios == 1
    assert set(buscar_pedidos()) == {pedido, otro}


def test_filtrar_por_estado_y_pago():
    pagado = PedidoFactory(estado_pago='pagado')
    PedidoFactory()
    assert list(buscar_pedidos(estado_pago='pagado')) == [pagado]
    assert list(buscar_pedidos(estado='completado')) == []


def test_quimicos_activos():
    activo = QuimicoFactory()
    QuimicoFactory(estado_actividad=False)
    assert list(quimicos_activos()) == [activo]


def _tomar(estudio, quimico):
    return tomar(estudio, quimico)


def test_filtrar_por_quimico_sin_duplicar_pedidos():
    quimico, otro = QuimicoFactory(), QuimicoFactory()
    pedido = PedidoFactory()
    _tomar(EstudioPedidoFactory(pedido=pedido), quimico)
    _tomar(EstudioPedidoFactory(pedido=pedido, estudio=Estudio.objects.get(clave='PLIP')), quimico)
    _tomar(EstudioPedidoFactory(), otro)
    encontrados = list(buscar_pedidos(quimico=quimico))
    assert encontrados == [pedido]
    assert encontrados[0].num_estudios == 2


def test_filtrar_por_fecha_del_pedido():
    hoy = timezone.localdate()
    viejo, nuevo = PedidoFactory(), PedidoFactory()
    Pedido.objects.filter(pk=viejo.pk).update(
        fecha_inicio=timezone.now() - datetime.timedelta(days=10)
    )
    assert list(buscar_pedidos(desde=hoy)) == [nuevo]
    assert list(buscar_pedidos(hasta=hoy - datetime.timedelta(days=1))) == [viejo]
    assert set(buscar_pedidos(desde=hoy - datetime.timedelta(days=10), hasta=hoy)) == {
        viejo,
        nuevo,
    }


def test_lista_de_trabajo_solo_en_proceso_y_a_su_cargo():
    quimico, otro = QuimicoFactory(), QuimicoFactory()
    primero = _tomar(EstudioPedidoFactory(), quimico)
    segundo = _tomar(EstudioPedidoFactory(), quimico)
    ajeno = _tomar(EstudioPedidoFactory(), otro)
    EstudioPedidoFactory()  # pendiente, en la cola
    completado = _tomar(EstudioPedidoFactory(), quimico)
    completado.estado = 'completado'
    completado.resultados = {}
    completado.fecha_completado = timezone.now()
    completado.save()
    assert list(lista_de_trabajo(quimico)) == [primero, segundo]
    assert list(lista_de_trabajo(otro)) == [ajeno]


def test_la_cola_solo_tiene_estudios_sin_encargado_de_citas_atendidas():
    viejo, nuevo = PedidoFactory(), PedidoFactory()
    Pedido.objects.filter(pk=viejo.pk).update(
        fecha_inicio=timezone.now() - datetime.timedelta(days=1)
    )
    plip = Estudio.objects.get(clave='PLIP')
    del_nuevo = EstudioPedidoFactory(pedido=nuevo)
    del_viejo = EstudioPedidoFactory(pedido=viejo)
    otro_del_viejo = EstudioPedidoFactory(pedido=viejo, estudio=plip)
    _tomar(EstudioPedidoFactory(estudio=plip), QuimicoFactory())
    EstudioPedidoFactory(pedido__cita__estado=EstadoCita.PROGRAMADA)
    # Agrupados por pedido, el más viejo primero.
    assert list(cola_de_estudios()) == [del_viejo, otro_del_viejo, del_nuevo]


def test_la_cola_por_paciente_junta_sus_pedidos():
    viejo = PedidoFactory()
    Pedido.objects.filter(pk=viejo.pk).update(
        fecha_inicio=timezone.now() - datetime.timedelta(days=2)
    )
    paciente = viejo.cita.paciente
    otro_pedido = PedidoFactory(cita__paciente=paciente)
    plip = Estudio.objects.get(clave='PLIP')
    primero = EstudioPedidoFactory(pedido=viejo)
    segundo = EstudioPedidoFactory(pedido=otro_pedido, estudio=plip)
    de_otro = EstudioPedidoFactory()

    grupos = cola_por_paciente()

    assert [g.paciente for g in grupos] == [paciente, de_otro.pedido.cita.paciente]
    assert grupos[0].estudios == [primero, segundo]
    assert grupos[0].pedidos == [viejo, otro_pedido]
    assert grupos[0].desde == Pedido.objects.get(pk=viejo.pk).fecha_inicio


def test_historial_de_paciente():
    actual = EstudioPedidoFactory()
    paciente = actual.pedido.cita.paciente
    anterior = EstudioPedidoFactory(
        pedido__cita__paciente=paciente,
        estado='completado',
        resultados={},
        fecha_completado=timezone.now(),
    )
    plip = EstudioPedidoFactory(
        pedido__cita__paciente=paciente, estudio=Estudio.objects.get(clave='PLIP')
    )
    EstudioPedidoFactory()  # de otro paciente
    assert set(historial_de_paciente(paciente)) == {actual, anterior, plip}
    assert list(historial_de_paciente(paciente, estudio=actual.estudio, excluir=actual)) == [
        anterior
    ]
