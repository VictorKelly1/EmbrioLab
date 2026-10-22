import datetime

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.utils import timezone

from apps.citas.models import Cita, EstadoCita, OrigenCita
from apps.citas.services import (
    TokenInvalido,
    TransicionInvalida,
    agendar_cita,
    cancelar_cita,
    consumir_token,
    generar_token_qr,
    marcar_atendida,
    marcar_no_atendida,
    obtener_cita_por_token,
    registrar_espontanea,
    reprogramar_cita,
)
from apps.citas.tests.factories import CitaFactory, en
from apps.citas.tokens import hash_token
from apps.core.services import dar_de_baja
from apps.cuentas.tests.factories import RecepcionistaFactory
from apps.pacientes.tests.factories import PacienteFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def recepcionista():
    return RecepcionistaFactory()


@pytest.fixture
def paciente():
    return PacienteFactory(
        persona__apellido_paterno='López', persona__apellido_materno='García', numero=15
    )


def _agendar(recepcionista, paciente, fecha_hora, **extra):
    return agendar_cita(
        recepcionista=recepcionista, paciente=paciente, fecha_hora=fecha_hora, **extra
    )


# Agendar


def test_agendar_cita(recepcionista, paciente):
    cita = _agendar(recepcionista, paciente, en(1, 10, 0), asunto=' Espermatobioscopia ')

    assert cita.estado == EstadoCita.PROGRAMADA
    assert cita.origen == OrigenCita.AGENDADA
    assert cita.fecha_fin - cita.fecha_hora == datetime.timedelta(minutes=30)
    assert cita.numero_folio == 'LOGA15'
    assert cita.asunto == 'Espermatobioscopia'
    assert cita.recordatorio_enviado is False


def test_el_folio_es_el_mismo_en_todas_las_citas(recepcionista, paciente):
    primera = _agendar(recepcionista, paciente, en(1, 10))
    segunda = _agendar(recepcionista, paciente, en(2, 10))
    assert primera.numero_folio == segunda.numero_folio == paciente.folio


@pytest.mark.parametrize(('hora', 'minuto'), [(10, 0), (10, 15), (9, 45), (10, 29)])
def test_no_se_empalman(recepcionista, paciente, hora, minuto):
    _agendar(recepcionista, paciente, en(1, 10, 0))
    with pytest.raises(ValidationError) as error:
        _agendar(recepcionista, PacienteFactory(), en(1, hora, minuto))
    assert 'Ya hay una cita a las 10:00' in error.value.message_dict['fecha_hora'][0]


@pytest.mark.parametrize(('hora', 'minuto'), [(10, 30), (9, 30)])
def test_citas_contiguas_si_se_permiten(recepcionista, paciente, hora, minuto):
    _agendar(recepcionista, paciente, en(1, 10, 0))
    _agendar(recepcionista, PacienteFactory(), en(1, hora, minuto))
    assert Cita.objects.count() == 2


def test_la_bd_rechaza_empalmes_aunque_se_salte_el_servicio(paciente):
    CitaFactory(paciente=paciente, fecha_hora=en(1, 10, 0))
    with pytest.raises(IntegrityError):
        CitaFactory(fecha_hora=en(1, 10, 10))


def test_la_bd_exige_30_minutos(paciente):
    cita = CitaFactory(paciente=paciente, fecha_hora=en(1, 10))
    with pytest.raises(IntegrityError):
        Cita.objects.filter(pk=cita.pk).update(fecha_fin=en(1, 11))


def test_no_se_agenda_en_el_pasado(recepcionista, paciente):
    with pytest.raises(ValidationError) as error:
        _agendar(recepcionista, paciente, en(-1, 10))
    assert 'fecha_hora' in error.value.message_dict


def test_no_se_agenda_a_un_paciente_dado_de_baja(recepcionista, paciente):
    dar_de_baja(paciente)
    with pytest.raises(ValidationError) as error:
        _agendar(recepcionista, paciente, en(1, 10))
    assert 'paciente' in error.value.message_dict


# Sin cita


def test_cita_espontanea_queda_atendida_a_esta_hora(recepcionista, paciente):
    cita = registrar_espontanea(recepcionista=recepcionista, paciente=paciente)

    assert cita.origen == OrigenCita.ESPONTANEA
    assert cita.estado == EstadoCita.ATENDIDA
    assert abs(cita.fecha_hora - timezone.now()) < datetime.timedelta(minutes=1)


def test_cita_espontanea_tambien_respeta_empalmes(recepcionista, paciente):
    ahora = timezone.now()
    CitaFactory(fecha_hora=ahora - datetime.timedelta(minutes=10))
    with pytest.raises(ValidationError):
        registrar_espontanea(recepcionista=recepcionista, paciente=paciente)


# Reprogramar, cancelar y estados


def test_reprogramar(recepcionista, paciente):
    cita = _agendar(recepcionista, paciente, en(1, 10))
    reprogramar_cita(cita, fecha_hora=en(2, 12, 30))
    cita.refresh_from_db()
    assert cita.fecha_hora == en(2, 12, 30)
    assert cita.fecha_fin == en(2, 13, 0)


def test_reprogramar_sobre_si_misma_no_es_empalme(recepcionista, paciente):
    cita = _agendar(recepcionista, paciente, en(1, 10))
    reprogramar_cita(cita, fecha_hora=en(1, 10, 15))
    assert Cita.objects.get().fecha_hora == en(1, 10, 15)


def test_reprogramar_respeta_empalmes(recepcionista, paciente):
    cita = _agendar(recepcionista, paciente, en(1, 10))
    _agendar(recepcionista, PacienteFactory(), en(1, 12))
    with pytest.raises(ValidationError):
        reprogramar_cita(cita, fecha_hora=en(1, 12, 15))


def test_cancelar_borra_la_cita(recepcionista, paciente):
    cita = _agendar(recepcionista, paciente, en(1, 10))
    cancelar_cita(cita)
    assert not Cita.objects.exists()


def test_marcar_atendida():
    cita = CitaFactory()
    marcar_atendida(cita)
    assert Cita.objects.get().estado == EstadoCita.ATENDIDA


def test_marcar_no_atendida_solo_despues_de_la_hora():
    futura = CitaFactory(fecha_hora=en(1, 10))
    with pytest.raises(TransicionInvalida):
        marcar_no_atendida(futura)

    pasada = CitaFactory(fecha_hora=en(-1, 10))
    marcar_no_atendida(pasada)
    assert Cita.objects.get(pk=pasada.pk).estado == EstadoCita.NO_ATENDIDA


@pytest.mark.parametrize(
    'accion',
    [
        marcar_atendida,
        marcar_no_atendida,
        cancelar_cita,
        lambda cita: reprogramar_cita(cita, fecha_hora=en(5, 10)),
    ],
)
def test_solo_las_programadas_cambian(accion):
    cita = CitaFactory(fecha_hora=en(-1, 10), estado=EstadoCita.ATENDIDA)
    with pytest.raises(TransicionInvalida):
        accion(cita)
    assert Cita.objects.get().estado == EstadoCita.ATENDIDA


# Token del formulario


def test_token_solo_guarda_el_hash():
    cita = CitaFactory()
    token = generar_token_qr(cita)

    cita.refresh_from_db()
    assert len(token) >= 40
    assert cita.token_qr == hash_token(token)
    assert token not in cita.token_qr
    assert obtener_cita_por_token(token) == cita


def test_token_vence_un_dia_despues_de_la_cita(settings):
    settings.CITAS_QR_HORAS_VIGENCIA = 24
    cita = CitaFactory(fecha_hora=en(3, 10))
    generar_token_qr(cita)
    assert cita.token_expiracion == en(4, 10)


def test_token_vencido():
    cita = CitaFactory()
    token = generar_token_qr(cita)
    Cita.objects.filter(pk=cita.pk).update(token_expiracion=timezone.now())
    with pytest.raises(TokenInvalido):
        obtener_cita_por_token(token)


def test_token_de_un_solo_uso():
    cita = CitaFactory()
    token = generar_token_qr(cita)
    consumir_token(cita)
    with pytest.raises(TokenInvalido):
        obtener_cita_por_token(token)


def test_generar_otro_token_invalida_el_anterior():
    cita = CitaFactory()
    viejo = generar_token_qr(cita)
    nuevo = generar_token_qr(cita)
    with pytest.raises(TokenInvalido):
        obtener_cita_por_token(viejo)
    assert obtener_cita_por_token(nuevo) == cita


@pytest.mark.parametrize('token', ['', 'inventado', 'x' * 43])
def test_token_desconocido(token):
    CitaFactory()
    with pytest.raises(TokenInvalido):
        obtener_cita_por_token(token)


def test_reprogramar_recalcula_el_vencimiento(recepcionista, paciente):
    cita = _agendar(recepcionista, paciente, en(1, 10))
    generar_token_qr(cita)
    reprogramar_cita(cita, fecha_hora=en(5, 10))
    assert cita.token_expiracion == en(6, 10)
