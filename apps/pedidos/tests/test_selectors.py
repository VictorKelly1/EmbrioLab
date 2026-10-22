import pytest

from apps.cuentas.tests.factories import QuimicoFactory
from apps.estudios.selectors import sugerir_estudios
from apps.pedidos.selectors import buscar_pedidos, quimicos_activos
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
