"""Citas agendadas sin paciente registrado (CONTEXTO.md §3)."""

import re

import pytest
from django.core import mail
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.urls import reverse

from apps.citas.models import Cita, EstadoCita
from apps.citas.services import (
    SinRegistro,
    agendar_cita,
    generar_token_qr,
    marcar_atendida,
    marcar_no_atendida,
    registrar_llegada,
    registrar_paciente_y_llegada,
)
from apps.citas.tests.factories import CitaFactory, en
from apps.cuentas.tests.factories import QuimicoFactory, RecepcionistaFactory
from apps.formularios.constructor import construir_formulario
from apps.formularios.selectors import version_para
from apps.notificaciones.models import Notificacion, TipoNotificacion
from apps.notificaciones.services import enviar_link_formulario, enviar_recordatorio
from apps.pacientes.models import Paciente
from apps.pacientes.tests.factories import PacienteFactory

pytestmark = pytest.mark.django_db

AGENDAR = reverse('citas:agendar')
SIN_REGISTRO = SinRegistro('  Ana  María ', ' Ruiz ', 'femenino', '55 1234 5678', '')


@pytest.fixture
def recepcionista():
    return RecepcionistaFactory()


@pytest.fixture
def recepcion(client, recepcionista):
    client.force_login(recepcionista.usuario)
    return client


@pytest.fixture
def cita(recepcionista):
    return agendar_cita(
        recepcionista=recepcionista, fecha_hora=en(1, 10), sin_registro=SIN_REGISTRO
    )


def _datos_paciente(**persona):
    return {
        'datos_persona': {
            'nombre': 'Ana María',
            'apellido_paterno': 'Ruiz',
            'apellido_materno': 'Soto',
            'genero': 'femenino',
            'fecha_nacimiento': '1990-05-04',
            'curp': 'RUSA900504MDFZTN09',
            'numero_ine': '',
            **persona,
        },
        'contactos': {'whatsapp': '5512345678', 'telefono': '', 'correo': ''},
    }


# Servicio


def test_agendar_sin_registro_guarda_lo_minimo(cita):
    assert cita.paciente is None
    assert (cita.nombre, cita.apellido_paterno, cita.genero) == ('Ana María', 'Ruiz', 'femenino')
    assert cita.telefono == '5512345678'
    assert cita.numero_folio == ''
    assert cita.nombre_paciente == 'Ana María Ruiz'
    assert cita.estado == EstadoCita.PROGRAMADA


@pytest.mark.parametrize(
    ('datos', 'campo'),
    [
        (SinRegistro('', 'Ruiz', 'femenino', '5512345678'), 'nombre'),
        (SinRegistro('Ana', ' ', 'femenino', '5512345678'), 'apellido_paterno'),
        (SinRegistro('Ana', 'Ruiz', '', '5512345678'), 'genero'),
        (SinRegistro('Ana', 'Ruiz', 'femenino'), 'telefono'),
        (SinRegistro('Ana', 'Ruiz', 'femenino', '123'), 'telefono'),
        (SinRegistro('Ana', 'Ruiz', 'femenino', '', 'no-es-correo'), 'correo'),
    ],
)
def test_agendar_sin_registro_valida(recepcionista, datos, campo):
    with pytest.raises(ValidationError) as error:
        agendar_cita(recepcionista=recepcionista, fecha_hora=en(1), sin_registro=datos)
    assert campo in error.value.message_dict
    assert not Cita.objects.exists()


def test_con_correo_basta(recepcionista):
    cita = agendar_cita(
        recepcionista=recepcionista,
        fecha_hora=en(1),
        sin_registro=SinRegistro('Ana', 'Ruiz', 'femenino', '', ' ANA@Example.com '),
    )
    assert (cita.telefono, cita.correo) == ('', 'ana@example.com')


def test_paciente_o_datos_pero_no_ambos(recepcionista):
    with pytest.raises(ValidationError):
        agendar_cita(recepcionista=recepcionista, fecha_hora=en(1))
    with pytest.raises(ValidationError):
        agendar_cita(
            recepcionista=recepcionista,
            fecha_hora=en(1),
            paciente=PacienteFactory(),
            sin_registro=SIN_REGISTRO,
        )


def test_tampoco_se_empalma(cita, recepcionista):
    with pytest.raises(ValidationError, match='ocupa ese horario'):
        agendar_cita(recepcionista=recepcionista, fecha_hora=en(1, 10), paciente=PacienteFactory())


def test_no_se_atiende_sin_registrar_la_llegada(cita):
    with pytest.raises(ValidationError, match='registre la llegada'):
        marcar_atendida(cita)


def test_si_no_llega_queda_sin_paciente(recepcionista):
    cita = CitaFactory(
        paciente=None,
        numero_folio='',
        nombre='Ana',
        apellido_paterno='Ruiz',
        genero='femenino',
        telefono='5512345678',
        fecha_hora=en(-1),
    )
    marcar_no_atendida(cita)
    cita.refresh_from_db()
    assert (cita.estado, cita.paciente) == (EstadoCita.NO_ATENDIDA, None)
    assert not Paciente.objects.exists()


def test_registrar_llegada_con_paciente_existente(cita):
    paciente = PacienteFactory()
    registrar_llegada(cita, paciente)
    cita.refresh_from_db()
    assert (cita.paciente, cita.estado) == (paciente, EstadoCita.ATENDIDA)
    assert cita.numero_folio == paciente.folio
    # Lo que dio al agendar se conserva.
    assert cita.nombre == 'Ana María'


def test_registrar_llegada_dos_veces(cita):
    registrar_llegada(cita, PacienteFactory())
    with pytest.raises(ValidationError):
        registrar_llegada(cita, PacienteFactory())


def test_registrar_llegada_con_paciente_de_baja(cita):
    with pytest.raises(ValidationError, match='baja'):
        registrar_llegada(cita, PacienteFactory(estado_actividad=False))


def test_registrar_paciente_nuevo_y_su_llegada(cita):
    paciente = registrar_paciente_y_llegada(cita, **_datos_paciente())
    cita.refresh_from_db()
    assert cita.paciente == paciente
    assert cita.estado == EstadoCita.ATENDIDA
    assert cita.numero_folio == paciente.folio


def test_si_la_llegada_falla_no_queda_el_paciente(cita):
    registrar_llegada(cita, PacienteFactory())
    with pytest.raises(ValidationError):
        registrar_paciente_y_llegada(cita, **_datos_paciente())
    assert not Paciente.objects.filter(persona__curp='RUSA900504MDFZTN09').exists()


def test_la_bd_exige_paciente_al_atender():
    with pytest.raises(IntegrityError):
        CitaFactory(
            paciente=None,
            numero_folio='',
            nombre='Ana',
            apellido_paterno='Ruiz',
            genero='femenino',
            telefono='5512345678',
            estado=EstadoCita.ATENDIDA,
        )


def test_la_bd_exige_los_datos_sin_paciente():
    with pytest.raises(IntegrityError):
        CitaFactory(paciente=None, numero_folio='', nombre='Ana', apellido_paterno='Ruiz')


# Recordatorio, link y formulario


def test_recordatorio_va_al_telefono_de_la_cita(cita, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        filas = enviar_recordatorio(cita)
    assert [(f.canal, f.destinatario) for f in filas] == [('whatsapp', '5512345678')]
    cita.refresh_from_db()
    assert cita.recordatorio_enviado


def test_link_por_correo_saluda_por_su_nombre(recepcionista, django_capture_on_commit_callbacks):
    cita = agendar_cita(
        recepcionista=recepcionista,
        fecha_hora=en(1),
        sin_registro=SinRegistro('Ana', 'Ruiz', 'femenino', '', 'ana@example.com'),
    )
    with django_capture_on_commit_callbacks(execute=True):
        enviar_link_formulario(cita)
    assert Notificacion.objects.get().tipo == TipoNotificacion.QR
    assert mail.outbox[0].to == ['ana@example.com']
    assert mail.outbox[0].body.startswith('Hola, Ana:')


def test_el_formulario_se_elige_por_su_genero(client, cita):
    token = generar_token_qr(cita)
    respuesta = client.get(reverse('formulario_publico', args=[token]))
    assert respuesta.status_code == 200
    assert 'Ruiz' not in respuesta.content.decode()
    femenino = version_para('femenino')
    campos = set(respuesta.context['form'].fields)
    assert campos == set(construir_formulario(femenino.esquema)().fields)
    assert campos != set(construir_formulario(version_para('masculino').esquema)().fields)


# Vistas


def test_agendar_sin_registro_desde_la_pantalla(recepcion):
    fecha_hora = en(2, 11, 30)
    respuesta = recepcion.post(
        AGENDAR,
        {
            'tipo': 'sin_registro',
            'nombre': 'Luis',
            'apellido_paterno': 'Mora',
            'genero': 'masculino',
            'telefono': '5598765432',
            'fecha': fecha_hora.date().isoformat(),
            'hora': '11:30',
        },
    )
    cita = Cita.objects.get()
    assert respuesta.url == reverse('citas:detalle', args=[cita.pk])
    assert (cita.paciente, cita.nombre_paciente) == (None, 'Luis Mora')


def test_agendar_sin_registro_con_errores(recepcion):
    respuesta = recepcion.post(
        AGENDAR,
        {
            'tipo': 'sin_registro',
            'nombre': 'Luis',
            'fecha': en(2).date().isoformat(),
            'hora': '11:30',
        },
    )
    assert respuesta.status_code == 200
    errores = respuesta.context['form'].errors
    assert {'apellido_paterno', 'genero', 'telefono'} <= set(errores)
    assert 'paciente' not in errores
    assert not Cita.objects.exists()


def test_registrado_sin_elegir_paciente(recepcion):
    respuesta = recepcion.post(
        AGENDAR, {'tipo': 'registrado', 'fecha': en(2).date().isoformat(), 'hora': '11:30'}
    )
    assert 'paciente' in respuesta.context['form'].errors


def test_detalle_y_calendario_muestran_el_nombre(recepcion, cita):
    detalle = recepcion.get(reverse('citas:detalle', args=[cita.pk])).content.decode()
    assert 'Ana María Ruiz' in detalle
    assert 'Sin registro' in detalle
    assert reverse('citas:llegada', args=[cita.pk]) in detalle
    assert 'value="atendida"' not in detalle
    calendario = recepcion.get(
        reverse('citas:calendario'), {'vista': 'dia', 'fecha': cita.fecha_hora.date().isoformat()}
    )
    assert 'Ana María Ruiz' in calendario.content.decode()


def test_llegada_con_paciente_existente(recepcion, cita):
    paciente = PacienteFactory(persona__nombre='Ana María', persona__apellido_paterno='Ruiz')
    url = reverse('citas:llegada', args=[cita.pk])
    pantalla = recepcion.get(url)
    assert paciente in pantalla.context['sugeridos']
    respuesta = recepcion.post(url, {'paciente': paciente.pk})
    assert respuesta.url == reverse('citas:detalle', args=[cita.pk])
    cita.refresh_from_db()
    assert (cita.paciente, cita.estado) == (paciente, EstadoCita.ATENDIDA)
    # Ya registrada, la pantalla de llegada regresa al detalle.
    assert recepcion.get(url).url == reverse('citas:detalle', args=[cita.pk])


def test_llegada_con_paciente_nuevo(recepcion, cita):
    url = f'{reverse("pacientes:crear")}?cita={cita.pk}'
    pantalla = recepcion.get(url)
    inicial = pantalla.context['form'].initial
    assert (inicial['nombre'], inicial['whatsapp'], inicial['genero']) == (
        'Ana María',
        '5512345678',
        'femenino',
    )
    datos = _datos_paciente()
    respuesta = recepcion.post(
        url, {**datos['datos_persona'], **datos['contactos'], 'pais': 'México'}
    )
    assert respuesta.status_code == 302, respuesta.context['form'].errors
    assert respuesta.url == reverse('citas:detalle', args=[cita.pk])
    cita.refresh_from_db()
    assert cita.paciente.persona.curp == 'RUSA900504MDFZTN09'
    assert cita.estado == EstadoCita.ATENDIDA


def test_el_quimico_no_registra_llegadas(client, cita):
    client.force_login(QuimicoFactory().usuario)
    assert client.get(reverse('citas:llegada', args=[cita.pk])).status_code == 403


def test_el_mensaje_no_lleva_el_token_completo_en_el_log(cita):
    """El link sale en el mensaje, pero solo el hash queda en la BD."""
    token = generar_token_qr(cita)
    cita.refresh_from_db()
    assert token not in cita.token_qr
    assert re.fullmatch(r'[0-9a-f]{64}', cita.token_qr)
