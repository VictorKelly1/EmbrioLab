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
from apps.pedidos.models import EstudioPedido
from apps.pedidos.selectors import encargado_del_paciente
from apps.pedidos.services import (
    Linea,
    agregar_estudio,
    cambiar_doctor,
    cambiar_estado_pago,
    cambiar_pago_pedido,
    completar_estudio,
    crear_pedido,
    guardar_borrador,
    pasar_paciente,
    quitar_estudio,
    recalcular_pedido,
    soltar_paciente,
    tomar_paciente,
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


# Cola de químicos: tomar, soltar y pasar al paciente (CONTEXTO.md §3)


def _paciente(estudio):
    return estudio.pedido.cita.paciente


def test_tomar_al_paciente_toma_todos_sus_pedidos(cita, recepcionista, catalogo):
    quimico = QuimicoFactory()
    uno = _pedido(cita, recepcionista, Linea(catalogo['GLU']), Linea(catalogo['PLIP']))
    otra_cita = CitaFactory(paciente=cita.paciente, estado=EstadoCita.ATENDIDA)
    dos = _pedido(otra_cita, recepcionista, Linea(catalogo['ESP']))
    ajeno = EstudioPedidoFactory()  # de otro paciente: no se toca

    tomados = tomar_paciente(cita.paciente, quimico=quimico)

    assert len(tomados) == 3
    for pedido in (uno, dos):
        pedido.refresh_from_db()
        assert pedido.estado == 'en_proceso'
        assert {(e.estado, e.quimico_encargado_id) for e in pedido.estudios.all()} == {
            ('en_proceso', quimico.pk)
        }
        assert all(e.fecha_toma for e in pedido.estudios.all())
    ajeno.refresh_from_db()
    assert (ajeno.estado, ajeno.quimico_encargado) == ('pendiente', None)
    assert encargado_del_paciente(cita.paciente) == quimico


def test_el_pedido_nace_sin_encargados(cita, recepcionista, catalogo):
    pedido = _pedido(cita, recepcionista, Linea(catalogo['GLU']))
    estudio = pedido.estudios.get()
    assert (estudio.estado, estudio.quimico_encargado) == ('pendiente', None)


def test_estudios_nuevos_quedan_con_el_encargado(cita, recepcionista, catalogo):
    quimico = QuimicoFactory()
    pedido = _pedido(cita, recepcionista, Linea(catalogo['GLU']))
    tomar_paciente(cita.paciente, quimico=quimico)

    agregado = agregar_estudio(pedido, Linea(catalogo['PLIP']), usuario=recepcionista.usuario)
    otra_cita = CitaFactory(paciente=cita.paciente, estado=EstadoCita.ATENDIDA)
    nuevo = _pedido(otra_cita, recepcionista, Linea(catalogo['ESP'])).estudios.get()

    for estudio in (agregado, nuevo):
        estudio.refresh_from_db()
        assert (estudio.estado, estudio.quimico_encargado) == ('en_proceso', quimico)
        assert estudio.fecha_toma is not None
    nuevo.pedido.refresh_from_db()
    assert nuevo.pedido.estado == 'en_proceso'


def test_sin_estudios_en_proceso_los_nuevos_van_a_la_cola(cita, recepcionista, catalogo):
    """Si el encargado ya completó todo, el paciente deja de tener encargado."""
    quimico = QuimicoFactory()
    pedido = _pedido(cita, recepcionista, Linea(catalogo['GLU']))
    tomar_paciente(cita.paciente, quimico=quimico)
    completar_estudio(pedido.estudios.get(), {'glucosa': Decimal(90)}, quimico=quimico)
    estudio = agregar_estudio(pedido, Linea(catalogo['PLIP']), usuario=recepcionista.usuario)
    assert (estudio.estado, estudio.quimico_encargado) == ('pendiente', None)


def test_con_encargado_dado_de_baja_los_nuevos_van_a_la_cola(cita, recepcionista, catalogo):
    quimico = QuimicoFactory()
    pedido = _pedido(cita, recepcionista, Linea(catalogo['GLU']))
    tomar_paciente(cita.paciente, quimico=quimico)
    quimico.estado_actividad = False
    quimico.save()
    estudio = agregar_estudio(pedido, Linea(catalogo['PLIP']), usuario=recepcionista.usuario)
    assert (estudio.estado, estudio.quimico_encargado) == ('pendiente', None)


def test_otro_quimico_no_toma_un_paciente_con_encargado():
    estudio = EstudioPedidoFactory()
    quimico = QuimicoFactory()
    tomar_paciente(_paciente(estudio), quimico=quimico)
    with pytest.raises(ValidationError, match='ya tiene a este paciente'):
        tomar_paciente(_paciente(estudio), quimico=QuimicoFactory())
    with pytest.raises(ValidationError, match='no tiene estudios en espera'):
        tomar_paciente(_paciente(estudio), quimico=quimico)


def test_sin_estudios_en_espera_no_hay_nada_que_tomar():
    estudio = EstudioPedidoFactory(
        estado='completado', resultados={'glucosa': '90'}, fecha_completado=timezone.now()
    )
    with pytest.raises(ValidationError, match='no tiene estudios en espera'):
        tomar_paciente(_paciente(estudio), quimico=QuimicoFactory())


def test_un_quimico_dado_de_baja_no_toma_pacientes():
    estudio = EstudioPedidoFactory()
    with pytest.raises(ValidationError, match='baja'):
        tomar_paciente(_paciente(estudio), quimico=QuimicoFactory(estado_actividad=False))


def test_no_se_toman_estudios_de_una_cita_no_atendida():
    estudio = EstudioPedidoFactory(pedido__cita__estado=EstadoCita.PROGRAMADA)
    with pytest.raises(ValidationError, match='no tiene estudios en espera'):
        tomar_paciente(_paciente(estudio), quimico=QuimicoFactory())


@pytest.mark.django_db(transaction=True)
def test_dos_quimicos_toman_al_mismo_paciente_a_la_vez():
    """El bloqueo del paciente deja entrar a uno; los demás reciben el aviso."""
    estudio = EstudioPedidoFactory(estudio=EstudioFactory(), version_estudio=1)
    paciente = _paciente(estudio)
    quimicos = [QuimicoFactory() for _ in range(4)]
    salida = threading.Barrier(len(quimicos))

    def tomar(quimico):
        try:
            salida.wait()
            tomar_paciente(paciente, quimico=quimico)
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


def test_soltar_regresa_al_paciente_a_la_cola(cita, recepcionista, catalogo):
    quimico = QuimicoFactory()
    pedido = _pedido(cita, recepcionista, Linea(catalogo['GLU']), Linea(catalogo['PLIP']))
    tomar_paciente(cita.paciente, quimico=quimico)
    soltados = soltar_paciente(cita.paciente, quimico=quimico)
    assert len(soltados) == 2
    pedido.refresh_from_db()
    assert pedido.estado == 'pendiente'
    assert {(e.estado, e.quimico_encargado, e.fecha_toma) for e in pedido.estudios.all()} == {
        ('pendiente', None, None)
    }
    assert encargado_del_paciente(cita.paciente) is None
    # Ya en la cola, otro lo puede tomar.
    tomar_paciente(cita.paciente, quimico=QuimicoFactory())


def test_soltar_no_toca_los_completados(cita, recepcionista, catalogo):
    quimico = QuimicoFactory()
    pedido = _pedido(cita, recepcionista, Linea(catalogo['GLU']), Linea(catalogo['PLIP']))
    tomar_paciente(cita.paciente, quimico=quimico)
    glu = pedido.estudios.get(estudio__clave='GLU')
    completar_estudio(glu, {'glucosa': Decimal(90)}, quimico=quimico)
    soltar_paciente(cita.paciente, quimico=quimico)
    glu.refresh_from_db()
    assert (glu.estado, glu.quimico_encargado) == ('completado', quimico)
    assert pedido.estudios.get(estudio__clave='PLIP').estado == 'pendiente'


def test_solo_el_encargado_suelta_o_pasa_al_paciente():
    estudio = EstudioPedidoFactory()
    tomar_paciente(_paciente(estudio), quimico=QuimicoFactory())
    intruso = QuimicoFactory()
    with pytest.raises(ValidationError, match='no está a su cargo'):
        soltar_paciente(_paciente(estudio), quimico=intruso)
    with pytest.raises(ValidationError, match='no está a su cargo'):
        pasar_paciente(_paciente(estudio), intruso, quimico=intruso)


def test_con_algo_capturado_ya_no_se_suelta_ni_se_pasa(cita, recepcionista, catalogo):
    quimico = QuimicoFactory()
    pedido = _pedido(cita, recepcionista, Linea(catalogo['GLU']), Linea(catalogo['PLIP']))
    tomar_paciente(cita.paciente, quimico=quimico)
    glu = pedido.estudios.get(estudio__clave='GLU')
    guardar_borrador(glu, {'glucosa': Decimal(90)}, quimico=quimico)
    with pytest.raises(ValidationError, match='Glucosa'):
        soltar_paciente(cita.paciente, quimico=quimico)
    with pytest.raises(ValidationError, match='ya no se puede soltar ni pasar'):
        pasar_paciente(cita.paciente, QuimicoFactory(), quimico=quimico)
    assert set(pedido.estudios.values_list('quimico_encargado', flat=True)) == {quimico.pk}


def test_un_borrador_vacio_no_impide_soltarlo():
    estudio = EstudioPedidoFactory()
    quimico = QuimicoFactory()
    tomar_paciente(_paciente(estudio), quimico=quimico)
    guardar_borrador(estudio, {}, quimico=quimico)
    estudio.refresh_from_db()
    assert estudio.resultados == {'version': 1, 'valores': {}}
    soltar_paciente(_paciente(estudio), quimico=quimico)


def test_no_se_suelta_un_paciente_en_la_cola():
    estudio = EstudioPedidoFactory()
    with pytest.raises(ValidationError, match='no está a su cargo'):
        soltar_paciente(_paciente(estudio), quimico=QuimicoFactory())


def test_pasar_al_paciente_a_otro_quimico(cita, recepcionista, catalogo):
    pedido = _pedido(cita, recepcionista, Linea(catalogo['GLU']), Linea(catalogo['PLIP']))
    quimico, otro = QuimicoFactory(), QuimicoFactory()
    tomar_paciente(cita.paciente, quimico=quimico)
    pasar_paciente(cita.paciente, otro, quimico=quimico)
    assert {(e.estado, e.quimico_encargado_id) for e in pedido.estudios.all()} == {
        ('en_proceso', otro.pk)
    }
    # Los estudios nuevos ya son del nuevo encargado.
    estudio = agregar_estudio(pedido, Linea(catalogo['ESP']), usuario=recepcionista.usuario)
    assert estudio.quimico_encargado == otro


def test_no_se_pasa_a_si_mismo_ni_a_uno_dado_de_baja():
    estudio = EstudioPedidoFactory()
    quimico = QuimicoFactory()
    tomar_paciente(_paciente(estudio), quimico=quimico)
    with pytest.raises(ValidationError, match='otro químico'):
        pasar_paciente(_paciente(estudio), quimico, quimico=quimico)
    with pytest.raises(ValidationError, match='baja'):
        pasar_paciente(_paciente(estudio), QuimicoFactory(estado_actividad=False), quimico=quimico)


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
