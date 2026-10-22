import datetime
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.utils import timezone

from apps.citas.models import EstadoCita
from apps.citas.tests.factories import CitaFactory
from apps.cuentas.tests.factories import QuimicoFactory, RecepcionistaFactory
from apps.estudios.models import Estudio, EstudioAlias
from apps.pacientes.tests.factories import DoctorFactory
from apps.pedidos.estados import TransicionInvalida
from apps.pedidos.models import EstudioPedido
from apps.pedidos.services import (
    Linea,
    actualizar_estudio_pedido,
    agregar_estudio,
    asignar_quimico,
    cambiar_doctor,
    cambiar_estado_pago,
    cambiar_pago_pedido,
    crear_pedido,
    quitar_estudio,
    recalcular_pedido,
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


# Químico


def test_asignar_quimico_lo_pone_en_proceso(cita, recepcionista, catalogo):
    quimico = QuimicoFactory()
    pedido = _pedido(cita, recepcionista, Linea(catalogo['GLU']), Linea(catalogo['PLIP']))
    glu = pedido.estudios.get(estudio__clave='GLU')
    asignar_quimico(glu, quimico, usuario=recepcionista.usuario)
    glu.refresh_from_db()
    pedido.refresh_from_db()
    assert (glu.estado, glu.quimico_asignado, glu.usuario_asignacion) == (
        'en_proceso',
        quimico,
        recepcionista.usuario,
    )
    assert glu.fecha_asignacion is not None
    assert pedido.estado == 'en_proceso'


def test_asignar_al_crear(cita, recepcionista, catalogo):
    quimico = QuimicoFactory()
    pedido = _pedido(cita, recepcionista, Linea(catalogo['GLU'], quimico=quimico))
    assert pedido.estudios.get().quimico_asignado == quimico
    assert pedido.estado == 'en_proceso'


def test_reasignar_en_proceso(recepcionista):
    estudio = EstudioPedidoFactory()
    asignar_quimico(estudio, QuimicoFactory(), usuario=recepcionista.usuario)
    otro = QuimicoFactory()
    asignar_quimico(estudio, otro, usuario=recepcionista.usuario)
    estudio.refresh_from_db()
    assert (estudio.estado, estudio.quimico_asignado) == ('en_proceso', otro)


def test_no_reasigna_un_completado(recepcionista):
    estudio = EstudioPedidoFactory(
        estado='completado',
        quimico_asignado=QuimicoFactory(),
        resultados={'glucosa': '90'},
        fecha_completado=timezone.now(),
    )
    with pytest.raises(TransicionInvalida):
        asignar_quimico(estudio, QuimicoFactory(), usuario=recepcionista.usuario)


def test_no_asigna_quimico_dado_de_baja(recepcionista):
    with pytest.raises(ValidationError, match='baja'):
        asignar_quimico(
            EstudioPedidoFactory(),
            QuimicoFactory(estado_actividad=False),
            usuario=recepcionista.usuario,
        )


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


def test_actualizar_fila_solo_cambia_lo_distinto(recepcionista):
    estudio = EstudioPedidoFactory()
    quimico = QuimicoFactory()
    actualizar_estudio_pedido(
        estudio, quimico=quimico, estado_pago='abonado', usuario=recepcionista.usuario
    )
    estudio.refresh_from_db()
    fecha = estudio.fecha_asignacion
    actualizar_estudio_pedido(
        estudio, quimico=quimico, estado_pago='pagado', usuario=recepcionista.usuario
    )
    estudio.refresh_from_db()
    assert (estudio.quimico_asignado, estudio.estado_pago) == (quimico, 'pagado')
    assert estudio.fecha_asignacion == fecha


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
        quimico_asignado=QuimicoFactory(),
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


def test_la_bd_no_permite_en_proceso_sin_quimico():
    with pytest.raises(IntegrityError):
        EstudioPedidoFactory(estado='en_proceso')
