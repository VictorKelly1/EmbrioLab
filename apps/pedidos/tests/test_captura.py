import datetime
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.cuentas.tests.factories import QuimicoFactory, RecepcionistaFactory
from apps.estudios.models import Estudio
from apps.estudios.tests.factories import EstudioFactory, ValorReferenciaFactory
from apps.pedidos.estados import TransicionInvalida
from apps.pedidos.resultados import ALTO, BAJO, filas, fuera_de_rango
from apps.pedidos.services import asignar_quimicos, completar_estudio, guardar_borrador
from apps.pedidos.tests.factories import EstudioPedidoFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def quimico():
    return QuimicoFactory()


def _asignado(quimico, clave='GLU', **extra):
    estudio = EstudioPedidoFactory(estudio=Estudio.objects.get(clave=clave), **extra)
    asignar_quimicos(estudio, [quimico], usuario=RecepcionistaFactory().usuario)
    estudio.refresh_from_db()
    return estudio


def _plip(**valores):
    datos = {'colesterol_total': 210, 'hdl': 45, 'trigliceridos': 150}
    return {clave: Decimal(valor) for clave, valor in {**datos, **valores}.items()}


# Borrador


def test_borrador_guarda_lo_capturado_sin_completar(quimico):
    estudio = _asignado(quimico, 'PLIP')
    guardar_borrador(estudio, {'colesterol_total': Decimal(210), 'hdl': None}, quimico=quimico)
    estudio.refresh_from_db()
    assert estudio.estado == 'en_proceso'
    assert estudio.resultados == {'version': 1, 'valores': {'colesterol_total': '210'}}
    assert estudio.quimico_completo is None


def test_borrador_se_puede_volver_a_guardar(quimico):
    estudio = _asignado(quimico)
    guardar_borrador(estudio, {'glucosa': Decimal(90)}, quimico=quimico)
    guardar_borrador(estudio, {'glucosa': Decimal(95)}, quimico=quimico)
    estudio.refresh_from_db()
    assert estudio.resultados['valores'] == {'glucosa': '95'}


def test_no_acepta_campos_ajenos_al_estudio(quimico):
    with pytest.raises(ValidationError, match='no son del estudio: ldl'):
        guardar_borrador(_asignado(quimico, 'PLIP'), {'ldl': Decimal(1)}, quimico=quimico)


# Quién y cuándo captura


def test_solo_captura_un_quimico_asignado(quimico):
    estudio = _asignado(quimico)
    with pytest.raises(ValidationError, match='no le fue asignado'):
        guardar_borrador(estudio, {'glucosa': Decimal(90)}, quimico=QuimicoFactory())


def test_cualquiera_de_los_asignados_puede_completar(quimico):
    otro = QuimicoFactory()
    estudio = _asignado(quimico)
    asignar_quimicos(estudio, [quimico, otro], usuario=RecepcionistaFactory().usuario)
    completar_estudio(estudio, {'glucosa': Decimal(90)}, quimico=otro)
    estudio.refresh_from_db()
    assert estudio.quimico_completo == otro


def test_no_captura_un_estudio_pendiente(quimico):
    with pytest.raises(TransicionInvalida, match='pendiente'):
        guardar_borrador(EstudioPedidoFactory(), {'glucosa': Decimal(90)}, quimico=quimico)


def test_un_completado_no_se_corrige(quimico):
    estudio = _asignado(quimico)
    completar_estudio(estudio, {'glucosa': Decimal(90)}, quimico=quimico)
    with pytest.raises(TransicionInvalida, match='completado'):
        completar_estudio(estudio, {'glucosa': Decimal(91)}, quimico=quimico)
    with pytest.raises(TransicionInvalida):
        guardar_borrador(estudio, {'glucosa': Decimal(91)}, quimico=quimico)


def test_sin_definicion_en_codigo(quimico):
    estudio = EstudioPedidoFactory(estudio=EstudioFactory(), version_estudio=1)
    asignar_quimicos(estudio, [quimico], usuario=RecepcionistaFactory().usuario)
    with pytest.raises(ValidationError, match='definición'):
        guardar_borrador(estudio, {}, quimico=quimico)


# Completar


def test_completar_calcula_y_copia_las_referencias(quimico):
    estudio = _asignado(quimico, 'PLIP')
    completar_estudio(estudio, _plip(), quimico=quimico)
    estudio.refresh_from_db()
    estudio.pedido.refresh_from_db()
    assert estudio.estado == 'completado'
    assert estudio.quimico_completo == quimico
    assert estudio.fecha_completado is not None
    assert estudio.version_estudio == 1
    resultados = estudio.resultados
    assert resultados['version'] == 1
    assert resultados['valores'] == {
        'colesterol_total': '210',
        'hdl': '45',
        'trigliceridos': '150',
        'ldl': '135',
        'indice_aterogenico': '4.7',
    }
    # Paciente masculino: el HDL de hombres; LDL calculado también tiene referencia.
    assert resultados['referencias']['hdl']['rango'] == '≥ 40 mg/dL'
    assert resultados['referencias']['ldl']['valor_maximo'] == '100'
    assert set(resultados['referencias']) == {'colesterol_total', 'hdl', 'trigliceridos', 'ldl'}
    # No está enviado: el pedido sigue en proceso.
    assert estudio.pedido.estado == 'en_proceso'


def test_completar_exige_todos_los_campos(quimico):
    estudio = _asignado(quimico, 'PLIP')
    with pytest.raises(ValidationError) as error:
        completar_estudio(estudio, {'colesterol_total': Decimal(200)}, quimico=quimico)
    assert set(error.value.message_dict) == {'hdl', 'trigliceridos'}
    estudio.refresh_from_db()
    assert estudio.estado == 'en_proceso'


def test_completar_aplica_las_reglas_de_la_definicion(quimico):
    estudio = _asignado(quimico, 'ESP')
    valores = {
        'volumen': Decimal('2.5'),
        'concentracion': Decimal(40),
        'movilidad_progresiva': Decimal(50),
        'movilidad_no_progresiva': Decimal(10),
        'inmoviles': Decimal(10),
        'aspecto': 'Normal',
    }
    with pytest.raises(ValidationError, match='sumar 100'):
        completar_estudio(estudio, valores, quimico=quimico)


def test_la_referencia_es_la_vigente_el_dia_de_la_cita(quimico):
    estudio = _asignado(quimico)
    dia_cita = timezone.localdate(estudio.pedido.cita.fecha_hora)
    ValorReferenciaFactory(valor_minimo=60, vigente_desde=dia_cita + datetime.timedelta(days=1))
    completar_estudio(estudio, {'glucosa': Decimal(65)}, quimico=quimico)
    estudio.refresh_from_db()
    assert estudio.resultados['referencias']['glucosa']['rango'] == '70 – 99 mg/dL'


def test_cambiar_la_referencia_despues_no_cambia_lo_completado(quimico):
    estudio = _asignado(quimico)
    completar_estudio(estudio, {'glucosa': Decimal(120)}, quimico=quimico)
    referencia = estudio.estudio.valores_referencia.get()
    referencia.valor_maximo = 130
    referencia.save()
    estudio.refresh_from_db()
    assert filas(estudio)[0].marca == ALTO


# Fuera de rango y filas para mostrar


@pytest.mark.parametrize(
    ('valor', 'esperado'),
    [('69.9', BAJO), ('70', ''), ('99', ''), ('99.5', ALTO), (None, ''), ('Normal', '')],
)
def test_fuera_de_rango(valor, esperado):
    assert fuera_de_rango(valor, {'valor_minimo': '70', 'valor_maximo': '99'}) == esperado


def test_fuera_de_rango_con_un_solo_limite_o_sin_referencia():
    assert fuera_de_rango('39', {'valor_minimo': '40', 'valor_maximo': None}) == BAJO
    assert fuera_de_rango('1000', {'valor_minimo': '40', 'valor_maximo': None}) == ''
    assert fuera_de_rango('1000', None) == ''


def test_filas_en_orden_de_la_definicion(quimico):
    estudio = _asignado(quimico, 'PLIP')
    completar_estudio(estudio, _plip(hdl=35, trigliceridos=450), quimico=quimico)
    estudio.refresh_from_db()
    por_clave = {f.clave: f for f in filas(estudio)}
    assert [f.clave for f in filas(estudio)] == [
        'colesterol_total',
        'hdl',
        'trigliceridos',
        'ldl',
        'indice_aterogenico',
    ]
    assert por_clave['hdl'].marca == BAJO
    assert por_clave['trigliceridos'].marca == ALTO
    assert por_clave['ldl'].valor == '—'
    assert por_clave['ldl'].calculado
    assert por_clave['indice_aterogenico'].referencia == ''


def test_filas_de_un_borrador_y_de_campos_viejos(quimico):
    estudio = _asignado(quimico)
    estudio.resultados = {'version': 1, 'valores': {'glucosa': '88', 'campo_viejo': '1'}}
    assert [(f.etiqueta, f.valor) for f in filas(estudio)] == [
        ('Glucosa en ayuno', '88'),
        ('campo_viejo', '1'),
    ]
    estudio.resultados = None
    assert filas(estudio) == []
