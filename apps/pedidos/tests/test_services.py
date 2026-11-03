import datetime
import threading
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection
from django.utils import timezone

from apps.citas.models import EstadoCita
from apps.citas.tests.factories import CitaFactory
from apps.cuentas.tests.factories import QuimicoFactory, RecepcionistaFactory
from apps.estudios.models import Estudio, EstudioAlias
from apps.estudios.tests.factories import EstudioFactory
from apps.pacientes.tests.factories import DoctorFactory
from apps.pedidos.estados import TransicionInvalida
from apps.pedidos.models import EstudioPedido
from apps.pedidos.services import (
    Linea,
    agregar_estudio,
    cambiar_doctor,
    cambiar_estado_pago,
    cambiar_pago_pedido,
    crear_pedido,
    guardar_borrador,
    quitar_estudio,
    reasignar_estudio,
    recalcular_pedido,
    soltar_estudio,
    tomar_estudio,
)
from apps.pedidos.tests.factories import EstudioPedidoFactory, PedidoFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def catalogo():
    return {e.clave: e for e in Estudio.objects.all()}


@pytest.fixture
def recepcionista():
    return RecepcionistaFactory()


@pytest.fixture
def cita():
    return CitaFactory(estado=EstadoCita.ATENDIDA)


def _pedido(cita, recepcionista, *lineas, **extra):
    return crear_pedido(cita=cita, recepcionista=recepcionista, lineas=list(lineas), **extra)


# Crear


def test_crear_pedido_copia_precio_y_version(cita, recepcionista, catalogo):
    doctor = DoctorFactory()
    pedido = _pedido(
        cita,
        recepcionista,
        Linea(catalogo['PLIP'], 'Perfil  de lípidos'),
        Linea(catalogo['GLU']),
        doctor=doctor,
    )
    assert pedido.numero == f'{timezone.localdate().year}-0001'
    assert (pedido.doctor, pedido.recepcionista) == (doctor, recepcionista)
    plip, glu = pedido.estudios.order_by('id')
    assert (plip.nombre_solicitado, plip.precio, plip.version_estudio) == (
        'Perfil de lípidos',
        Decimal('450.00'),
        1,
    )
    assert glu.nombre_solicitado == 'Glucosa en ayuno'
    assert (pedido.estado, pedido.estado_pago, pedido.total_pago) == (
        'pendiente',
        'pendiente',
        Decimal('570.00'),
    )


def test_el_precio_del_pedido_no_cambia_con_el_catalogo(cita, recepcionista, catalogo):
    pedido = _pedido(cita, recepcionista, Linea(catalogo['GLU']))
    Estudio.objects.filter(clave='GLU').update(precio=999)
    assert pedido.estudios.get().precio == Decimal('120.00')


@pytest.mark.parametrize('estado', [EstadoCita.PROGRAMADA, EstadoCita.NO_ATENDIDA])
def test_solo_de_citas_atendidas(recepcionista, catalogo, estado):
    with pytest.raises(ValidationError, match='atendida'):
        _pedido(CitaFactory(estado=estado), recepcionista, Linea(catalogo['GLU']))


def test_sin_estudios(cita, recepcionista):
    with pytest.raises(ValidationError, match='al menos un estudio'):
        _pedido(cita, recepcionista)


def test_estudio_repetido(cita, recepcionista, catalogo):
    with pytest.raises(ValidationError, match='repetido'):
        _pedido(cita, recepcionista, Linea(catalogo['GLU']), Linea(catalogo['GLU'], 'glucosa'))


def test_estudio_inactivo(cita, recepcionista, catalogo):
    Estudio.objects.filter(clave='GLU').update(activo=False)
    catalogo['GLU'].refresh_from_db()
    with pytest.raises(ValidationError, match='activo'):
        _pedido(cita, recepcionista, Linea(catalogo['GLU']))


def test_una_cita_puede_tener_varios_pedidos(cita, recepcionista, catalogo):
    primero = _pedido(cita, recepcionista, Linea(catalogo['GLU']))
    segundo = _pedido(cita, recepcionista, Linea(catalogo['GLU']))
    assert primero.numero != segundo.numero
    assert cita.pedidos.count() == 2


def test_si_falla_no_queda_nada(cita, recepcionista, catalogo):
    with pytest.raises(ValidationError):
        _pedido(
            cita,
            recepcionista,
            Linea(catalogo['GLU'], 'glucosa', guardar_alias=True),
            Linea(catalogo['PLIP'], 'glicemia', guardar_alias=True),
        )
    assert not cita.pedidos.exists()
    # Y el número no se gastó.
    assert _pedido(cita, recepcionista, Linea(catalogo['GLU'])).numero.endswith('-0001')


# Alias desde el pedido


def test_guarda_el_nombre_como_alias_nuevo(cita, recepcionista, catalogo):
    _pedido(cita, recepcionista, Linea(catalogo['PLIP'], 'Lípidos completos', guardar_alias=True))
    alias = EstudioAlias.objects.get(alias='lipidos completos')
    assert alias.estudio == catalogo['PLIP']
    assert alias.usuario_registro == recepcionista.usuario


def test_alias_que_ya_existe_para_el_mismo_estudio_no_falla(cita, recepcionista, catalogo):
    _pedido(cita, recepcionista, Linea(catalogo['GLU'], 'Glicemia', guardar_alias=True))
    assert EstudioAlias.objects.filter(alias='glicemia').count() == 1


def test_alias_de_otro_estudio_avisa(cita, recepcionista, catalogo):
    with pytest.raises(ValidationError, match='ya es alias de Glucosa en ayuno'):
        _pedido(cita, recepcionista, Linea(catalogo['PLIP'], 'glicemia', guardar_alias=True))


def test_no_guarda_alias_igual_al_nombre(cita, recepcionista, catalogo):
    antes = EstudioAlias.objects.count()
    _pedido(cita, recepcionista, Linea(catalogo['GLU'], 'GLUCOSA EN AYUNO', guardar_alias=True))
    assert EstudioAlias.objects.count() == antes


# Cola de químicos: tomar, soltar y pasar


def test_tomar_un_estudio_lo_deja_a_su_cargo_y_en_proceso(cita, recepcionista, catalogo):
    quimico = QuimicoFactory()
    pedido = _pedido(cita, recepcionista, Linea(catalogo['GLU']), Linea(catalogo['PLIP']))
    glu = pedido.estudios.get(estudio__clave='GLU')
    tomar_estudio(glu, quimico=quimico)
    glu.refresh_from_db()
    pedido.refresh_from_db()
    assert (glu.estado, glu.quimico_encargado) == ('en_proceso', quimico)
    assert glu.fecha_toma is not None
    assert pedido.estado == 'en_proceso'


def test_un_quimico_puede_tomar_varios_estudios_del_mismo_pedido(cita, recepcionista, catalogo):
    quimico = QuimicoFactory()
    pedido = _pedido(cita, recepcionista, Linea(catalogo['GLU']), Linea(catalogo['PLIP']))
    for estudio in pedido.estudios.all():
        tomar_estudio(estudio, quimico=quimico)
    assert set(pedido.estudios.values_list('quimico_encargado', flat=True)) == {quimico.pk}


def test_el_pedido_nace_sin_encargados(cita, recepcionista, catalogo):
    pedido = _pedido(cita, recepcionista, Linea(catalogo['GLU']))
    estudio = pedido.estudios.get()
    assert (estudio.estado, estudio.quimico_encargado) == ('pendiente', None)


def test_no_se_toma_un_estudio_que_ya_tiene_encargado():
    estudio = EstudioPedidoFactory()
    quimico = QuimicoFactory()
    tomar_estudio(estudio, quimico=quimico)
    with pytest.raises(ValidationError, match='Otro químico ya tomó'):
        tomar_estudio(estudio, quimico=QuimicoFactory())
    with pytest.raises(ValidationError, match='Ya tiene este estudio'):
        tomar_estudio(estudio, quimico=quimico)


def test_no_se_toma_un_completado():
    estudio = EstudioPedidoFactory(
        estado='completado', resultados={'glucosa': '90'}, fecha_completado=timezone.now()
    )
    with pytest.raises(TransicionInvalida):
        tomar_estudio(estudio, quimico=QuimicoFactory())


def test_un_quimico_dado_de_baja_no_toma_estudios():
    with pytest.raises(ValidationError, match='baja'):
        tomar_estudio(EstudioPedidoFactory(), quimico=QuimicoFactory(estado_actividad=False))


def test_no_se_toma_un_estudio_de_una_cita_no_atendida():
    estudio = EstudioPedidoFactory(pedido__cita__estado=EstadoCita.PROGRAMADA)
    with pytest.raises(ValidationError, match='atendida'):
        tomar_estudio(estudio, quimico=QuimicoFactory())


@pytest.mark.django_db(transaction=True)
def test_dos_quimicos_toman_el_mismo_estudio_a_la_vez():
    """El bloqueo de la fila deja entrar a uno; el otro recibe el aviso."""
    estudio = EstudioPedidoFactory(estudio=EstudioFactory(), version_estudio=1)
    quimicos = [QuimicoFactory() for _ in range(4)]
    salida = threading.Barrier(len(quimicos))

    def tomar(quimico):
        try:
            salida.wait()
            tomar_estudio(estudio, quimico=quimico)
            return 'tomado'
        except ValidationError:
            return 'rechazado'
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=len(quimicos)) as hilos:
        resultados = list(hilos.map(tomar, quimicos))
    assert sorted(resultados) == ['rechazado'] * 3 + ['tomado']
    estudio.refresh_from_db()
    assert estudio.quimico_encargado == quimicos[resultados.index('tomado')]


def test_soltar_lo_regresa_a_la_cola():
    estudio = EstudioPedidoFactory()
    quimico = QuimicoFactory()
    tomar_estudio(estudio, quimico=quimico)
    soltar_estudio(estudio, quimico=quimico)
    estudio.refresh_from_db()
    estudio.pedido.refresh_from_db()
    assert (estudio.estado, estudio.quimico_encargado, estudio.fecha_toma) == (
        'pendiente',
        None,
        None,
    )
    assert estudio.pedido.estado == 'pendiente'
    # Ya en la cola, otro lo puede tomar.
    tomar_estudio(estudio, quimico=QuimicoFactory())


def test_solo_el_encargado_suelta_o_pasa_el_estudio():
    estudio = EstudioPedidoFactory()
    tomar_estudio(estudio, quimico=QuimicoFactory())
    intruso = QuimicoFactory()
    with pytest.raises(ValidationError, match='no está a su cargo'):
        soltar_estudio(estudio, quimico=intruso)
    with pytest.raises(ValidationError, match='no está a su cargo'):
        reasignar_estudio(estudio, intruso, quimico=intruso)


def test_con_borrador_ya_no_se_suelta_ni_se_pasa():
    estudio = EstudioPedidoFactory()
    quimico = QuimicoFactory()
    tomar_estudio(estudio, quimico=quimico)
    guardar_borrador(estudio, {'glucosa': Decimal(90)}, quimico=quimico)
    with pytest.raises(ValidationError, match='borrador'):
        soltar_estudio(estudio, quimico=quimico)
    with pytest.raises(ValidationError, match='borrador'):
        reasignar_estudio(estudio, QuimicoFactory(), quimico=quimico)


def test_un_borrador_vacio_no_impide_soltarlo():
    estudio = EstudioPedidoFactory()
    quimico = QuimicoFactory()
    tomar_estudio(estudio, quimico=quimico)
    guardar_borrador(estudio, {}, quimico=quimico)
    estudio.refresh_from_db()
    assert estudio.resultados == {'version': 1, 'valores': {}}
    soltar_estudio(estudio, quimico=quimico)


def test_no_se_suelta_un_pendiente():
    with pytest.raises(TransicionInvalida, match='pendiente'):
        soltar_estudio(EstudioPedidoFactory(), quimico=QuimicoFactory())


def test_pasar_el_estudio_a_otro_quimico():
    estudio = EstudioPedidoFactory()
    quimico, otro = QuimicoFactory(), QuimicoFactory()
    tomar_estudio(estudio, quimico=quimico)
    reasignar_estudio(estudio, otro, quimico=quimico)
    estudio.refresh_from_db()
    assert (estudio.estado, estudio.quimico_encargado) == ('en_proceso', otro)


def test_no_se_pasa_a_si_mismo_ni_a_uno_dado_de_baja():
    estudio = EstudioPedidoFactory()
    quimico = QuimicoFactory()
    tomar_estudio(estudio, quimico=quimico)
    with pytest.raises(ValidationError, match='otro químico'):
        reasignar_estudio(estudio, quimico, quimico=quimico)
    with pytest.raises(ValidationError, match='baja'):
        reasignar_estudio(estudio, QuimicoFactory(estado_actividad=False), quimico=quimico)


def test_la_bd_exige_encargado_en_proceso():
    with pytest.raises(IntegrityError):
        EstudioPedidoFactory(estado='en_proceso')


def test_la_bd_no_deja_encargado_en_un_pendiente():
    with pytest.raises(IntegrityError):
        EstudioPedidoFactory(quimico_encargado=QuimicoFactory(), fecha_toma=timezone.now())


# Pago


def test_pago_por_estudio_y_derivado_del_pedido(cita, recepcionista, catalogo):
    pedido = _pedido(cita, recepcionista, Linea(catalogo['GLU']), Linea(catalogo['PLIP']))
    glu, plip = pedido.estudios.order_by('id')
    cambiar_estado_pago(glu, 'pagado')
    pedido.refresh_from_db()
    assert pedido.estado_pago == 'abonado'
    cambiar_estado_pago(plip, 'pagado')
    pedido.refresh_from_db()
    assert pedido.estado_pago == 'pagado'


def test_pago_invalido():
    with pytest.raises(ValidationError):
        cambiar_estado_pago(EstudioPedidoFactory(), 'regalado')


def test_pagar_todo_el_pedido(cita, recepcionista, catalogo):
    pedido = _pedido(cita, recepcionista, Linea(catalogo['GLU']), Linea(catalogo['PLIP']))
    pedido = cambiar_pago_pedido(pedido, 'pagado')
    assert pedido.estado_pago == 'pagado'
    assert set(pedido.estudios.values_list('estado_pago', flat=True)) == {'pagado'}


# Agregar, quitar y doctor


def test_agregar_y_quitar_estudio(cita, recepcionista, catalogo):
    pedido = _pedido(cita, recepcionista, Linea(catalogo['GLU']))
    nuevo = agregar_estudio(pedido, Linea(catalogo['ESP']), usuario=recepcionista.usuario)
    pedido.refresh_from_db()
    assert pedido.total_pago == Decimal('920.00')
    quitar_estudio(nuevo)
    pedido.refresh_from_db()
    assert pedido.total_pago == Decimal('120.00')


def test_no_agrega_estudio_repetido(cita, recepcionista, catalogo):
    pedido = _pedido(cita, recepcionista, Linea(catalogo['GLU']))
    with pytest.raises(ValidationError, match='ya está'):
        agregar_estudio(pedido, Linea(catalogo['GLU']), usuario=recepcionista.usuario)


def test_no_quita_el_ultimo_estudio(cita, recepcionista, catalogo):
    pedido = _pedido(cita, recepcionista, Linea(catalogo['GLU']))
    with pytest.raises(ValidationError, match='al menos un estudio'):
        quitar_estudio(pedido.estudios.get())


def test_cambiar_doctor(cita, recepcionista, catalogo):
    pedido = _pedido(cita, recepcionista, Linea(catalogo['GLU']))
    doctor = DoctorFactory()
    assert cambiar_doctor(pedido, doctor).doctor == doctor
    assert cambiar_doctor(pedido, None).doctor is None


# Derivados


def _completar(estudio, enviado=None):
    EstudioPedido.objects.filter(pk=estudio.pk).update(
        estado='completado',
        resultados={},
        fecha_completado=timezone.now() - datetime.timedelta(hours=1),
        fecha_envio=enviado,
    )


def test_recalcular_completado_cuando_todo_esta_enviado():
    pedido = PedidoFactory()
    uno, dos = (
        EstudioPedidoFactory(pedido=pedido),
        EstudioPedidoFactory(pedido=pedido, estudio=Estudio.objects.get(clave='PLIP')),
    )
    _completar(uno, enviado=timezone.now())
    _completar(dos)
    pedido = recalcular_pedido(pedido)
    assert pedido.estado == 'en_proceso'
    assert pedido.fecha_completado is not None
    assert pedido.fecha_envio is None
    ahora = timezone.now()
    EstudioPedido.objects.filter(pk=dos.pk).update(fecha_envio=ahora)
    pedido = recalcular_pedido(pedido)
    assert (pedido.estado, pedido.fecha_envio) == ('completado', ahora)
    assert pedido.estado_pago == 'pendiente'


def test_la_bd_no_permite_enviar_sin_completar():
    with pytest.raises(IntegrityError):
        EstudioPedidoFactory(fecha_envio=timezone.now())
