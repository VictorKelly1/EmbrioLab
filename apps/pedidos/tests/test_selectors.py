import datetime

import pytest
from django.utils import timezone

from apps.cuentas.tests.factories import QuimicoFactory, RecepcionistaFactory
from apps.estudios.models import Estudio
from apps.estudios.selectors import sugerir_estudios
from apps.pedidos.models import Pedido
from apps.pedidos.selectors import (
    buscar_pedidos,
    historial_de_paciente,
    lista_de_trabajo,
    quimicos_activos,
)
from apps.pedidos.services import asignar_quimicos
from apps.pedidos.tests.factories import EstudioPedidoFactory, PedidoFactory

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


def _asignar(estudio, *quimicos):
    asignar_quimicos(estudio, list(quimicos), usuario=RecepcionistaFactory().usuario)
    estudio.refresh_from_db()
    return estudio


def test_filtrar_por_quimico_sin_duplicar_pedidos():
    quimico, otro = QuimicoFactory(), QuimicoFactory()
    pedido = PedidoFactory()
    _asignar(EstudioPedidoFactory(pedido=pedido), quimico)
    _asignar(
        EstudioPedidoFactory(pedido=pedido, estudio=Estudio.objects.get(clave='PLIP')),
        quimico,
        otro,
    )
    _asignar(EstudioPedidoFactory(), otro)
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


def test_lista_de_trabajo_solo_en_proceso_y_asignados():
    quimico, otro = QuimicoFactory(), QuimicoFactory()
    primero = _asignar(EstudioPedidoFactory(), quimico, otro)
    segundo = _asignar(EstudioPedidoFactory(), quimico)
    _asignar(EstudioPedidoFactory(), otro)
    EstudioPedidoFactory()  # pendiente, sin químico
    completado = _asignar(EstudioPedidoFactory(), quimico)
    completado.estado = 'completado'
    completado.resultados = {}
    completado.fecha_completado = timezone.now()
    completado.save()
    assert list(lista_de_trabajo(quimico)) == [primero, segundo]
    assert list(lista_de_trabajo(otro))[0] == primero


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
