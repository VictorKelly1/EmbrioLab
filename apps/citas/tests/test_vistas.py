import datetime

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.citas.models import Cita, EstadoCita, OrigenCita
from apps.citas.services import generar_token_qr
from apps.citas.tests.factories import CitaFactory, en
from apps.cuentas.tests.factories import AdminFactory, QuimicoFactory, RecepcionistaFactory
from apps.pacientes.tests.factories import PacienteFactory

pytestmark = pytest.mark.django_db

CALENDARIO = reverse('citas:calendario')
AGENDAR = reverse('citas:agendar')
ESPONTANEA = reverse('citas:espontanea')


@pytest.fixture
def recepcionista():
    return RecepcionistaFactory()


@pytest.fixture
def recepcion(client, recepcionista):
    client.force_login(recepcionista.usuario)
    return client


@pytest.fixture
def paciente():
    return PacienteFactory(persona__nombre='Ana', persona__apellido_paterno='López')


# Permisos


@pytest.mark.parametrize('fabrica', [QuimicoFactory, AdminFactory])
def test_solo_la_recepcionista(client, fabrica):
    client.force_login(fabrica().usuario)
    cita = CitaFactory()
    assert client.get(CALENDARIO).status_code == 403
    assert client.get(AGENDAR).status_code == 403
    assert client.get(reverse('citas:detalle', args=[cita.pk])).status_code == 403
    assert (
        client.post(reverse('citas:accion', args=[cita.pk]), {'accion': 'cancelar'}).status_code
        == 403
    )
    assert Cita.objects.exists()


def test_sin_sesion_redirige(client):
    assert client.get(CALENDARIO).status_code == 302


# Calendario


def test_calendario_semana_y_dia(recepcion, paciente):
    cita = CitaFactory(paciente=paciente, fecha_hora=en(1, 10, 0))
    fecha = cita.fecha_hora.date().isoformat()

    semana = recepcion.get(CALENDARIO, {'fecha': fecha})
    assert semana.status_code == 200
    assert 'Ana López' in semana.text
    assert reverse('citas:detalle', args=[cita.pk]) in semana.text

    dia = recepcion.get(CALENDARIO, {'vista': 'dia', 'fecha': fecha})
    assert cita.numero_folio in dia.text


def test_cita_en_domingo_aparece_en_la_semana(recepcion):
    hoy = timezone.localdate()
    domingo = hoy + datetime.timedelta(days=6 - hoy.weekday() + 7)
    fecha_hora = timezone.make_aware(datetime.datetime.combine(domingo, datetime.time(11)))
    cita = CitaFactory(fecha_hora=fecha_hora)
    respuesta = recepcion.get(CALENDARIO, {'fecha': domingo.isoformat()})
    assert reverse('citas:detalle', args=[cita.pk]) in respuesta.text
    lunes = domingo - datetime.timedelta(days=6)
    respuesta = recepcion.get(CALENDARIO, {'fecha': lunes.isoformat()})
    assert reverse('citas:detalle', args=[cita.pk]) in respuesta.text


def test_calendario_con_parametros_invalidos(recepcion):
    assert recepcion.get(CALENDARIO, {'vista': 'x', 'fecha': 'no-es-fecha'}).status_code == 200


def test_huecos_futuros_llevan_a_agendar(recepcion):
    respuesta = recepcion.get(CALENDARIO, {'vista': 'dia', 'fecha': en(1).date().isoformat()})
    assert f'{AGENDAR}?fecha_hora=' in respuesta.text


def test_sin_consultas_n_mas_1(recepcion):
    def consultas():
        with CaptureQueriesContext(connection) as contexto:
            recepcion.get(CALENDARIO, {'fecha': en(1).date().isoformat()})
        return len(contexto)

    CitaFactory(fecha_hora=en(1, 9))
    antes = consultas()
    for hora in (10, 11, 12, 13):
        CitaFactory(fecha_hora=en(1, hora))
    assert consultas() == antes


# Agendar y sin cita


def test_agendar(recepcion, recepcionista, paciente):
    fecha_hora = en(2, 11, 30)
    respuesta = recepcion.post(
        AGENDAR,
        {
            'paciente': paciente.pk,
            'fecha': fecha_hora.date().isoformat(),
            'hora': '11:30',
            'asunto': 'Biometría',
        },
    )
    cita = Cita.objects.get()
    assert respuesta.status_code == 302
    assert respuesta.url == reverse('citas:detalle', args=[cita.pk])
    assert cita.fecha_hora == fecha_hora
    assert cita.recepcionista == recepcionista


def test_agendar_precarga_paciente_y_horario(recepcion, paciente):
    respuesta = recepcion.get(AGENDAR, {'paciente': paciente.pk, 'fecha_hora': '2030-01-02T09:30'})
    assert respuesta.context['form'].initial['hora'].strftime('%H:%M') == '09:30'
    assert respuesta.context['paciente_elegido'] == paciente


def test_agendar_empalmada_sugiere_horario(recepcion, paciente):
    CitaFactory(fecha_hora=en(2, 10, 0))
    respuesta = recepcion.post(
        AGENDAR,
        {'paciente': paciente.pk, 'fecha': en(2).date().isoformat(), 'hora': '10:15'},
    )
    assert respuesta.status_code == 200
    errores = respuesta.context['form'].non_field_errors()
    assert any('Ya hay una cita a las 10:00' in e for e in errores)
    assert any('Siguiente horario libre' in e and '10:30' in e for e in errores)
    assert Cita.objects.count() == 1


def test_agendar_sin_paciente(recepcion):
    respuesta = recepcion.post(AGENDAR, {'fecha': en(2).date().isoformat(), 'hora': '10:00'})
    assert 'paciente' in respuesta.context['form'].errors


def test_buscar_paciente(recepcion, paciente):
    respuesta = recepcion.get(reverse('citas:buscar_paciente'), {'q': 'lopez'})
    assert f'data-paciente="{paciente.pk}"' in respuesta.text


def test_atender_sin_cita(recepcion, paciente):
    respuesta = recepcion.post(ESPONTANEA, {'paciente': paciente.pk, 'hora': '00:01'})
    cita = Cita.objects.get()
    assert respuesta.status_code == 302
    assert cita.origen == OrigenCita.ESPONTANEA
    assert cita.estado == EstadoCita.ATENDIDA


# Detalle y acciones


def test_marcar_atendida(recepcion):
    cita = CitaFactory()
    recepcion.post(reverse('citas:accion', args=[cita.pk]), {'accion': 'atendida'})
    cita.refresh_from_db()
    assert cita.estado == EstadoCita.ATENDIDA


def test_no_asistio_antes_de_la_hora_muestra_error(recepcion):
    cita = CitaFactory(fecha_hora=en(1, 10))
    respuesta = recepcion.post(
        reverse('citas:accion', args=[cita.pk]), {'accion': 'no_atendida'}, follow=True
    )
    assert 'todavía no empieza' in respuesta.text
    cita.refresh_from_db()
    assert cita.estado == EstadoCita.PROGRAMADA


def test_accion_desconocida(recepcion):
    cita = CitaFactory()
    assert (
        recepcion.post(reverse('citas:accion', args=[cita.pk]), {'accion': 'x'}).status_code == 404
    )


def test_cancelar_borra(recepcion):
    cita = CitaFactory()
    respuesta = recepcion.post(reverse('citas:accion', args=[cita.pk]), {'accion': 'cancelar'})
    assert respuesta.url == CALENDARIO
    assert not Cita.objects.exists()


def test_reprogramar(recepcion):
    cita = CitaFactory(fecha_hora=en(1, 10))
    destino = en(3, 16, 30)
    recepcion.post(
        reverse('citas:reprogramar', args=[cita.pk]),
        {'fecha': destino.date().isoformat(), 'hora': '16:30'},
    )
    cita.refresh_from_db()
    assert cita.fecha_hora == destino


def test_reprogramar_con_error_vuelve_al_detalle(recepcion):
    cita = CitaFactory(fecha_hora=en(1, 10))
    respuesta = recepcion.post(
        reverse('citas:reprogramar', args=[cita.pk]),
        {'fecha': en(-2).date().isoformat(), 'hora': '10:00'},
    )
    assert respuesta.status_code == 200
    assert 'Elija una fecha y hora futuras.' in respuesta.text


def test_generar_link_muestra_qr_una_vez(recepcion):
    cita = CitaFactory()
    respuesta = recepcion.post(reverse('citas:generar_qr', args=[cita.pk]))
    assert respuesta.status_code == 200
    assert '<svg' in respuesta.text
    link = respuesta.context['link']
    assert '/f/' in link

    cita.refresh_from_db()
    assert cita.token_qr
    detalle = recepcion.get(reverse('citas:detalle', args=[cita.pk]))
    assert link not in detalle.text


def test_detalle_inexistente(recepcion):
    assert recepcion.get(reverse('citas:detalle', args=[999])).status_code == 404


# Página pública del link


def test_link_publico_valido_sin_datos_del_paciente(client, paciente):
    cita = CitaFactory(paciente=paciente)
    token = generar_token_qr(cita)
    respuesta = client.get(reverse('formulario_publico', args=[token]))
    assert respuesta.status_code == 200
    assert 'Ana' not in respuesta.text
    assert cita.numero_folio not in respuesta.text


def test_link_publico_invalido(client):
    respuesta = client.get(reverse('formulario_publico', args=['inventado']))
    assert respuesta.status_code == 404
    assert 'ya no está disponible' in respuesta.text


# Integración con otras pantallas


def test_detalle_del_paciente_muestra_sus_citas(recepcion, paciente):
    CitaFactory(paciente=paciente, asunto='Cultivo')
    respuesta = recepcion.get(reverse('pacientes:detalle', args=[paciente.pk]))
    assert 'Cultivo' in respuesta.text
    assert f'{AGENDAR}?paciente={paciente.pk}' in respuesta.text


def test_inicio_de_la_recepcionista_muestra_citas_de_hoy(recepcion, paciente):
    CitaFactory(paciente=paciente, fecha_hora=en(0, 23, 0))
    respuesta = recepcion.get(reverse('inicio'))
    assert 'Citas de hoy' in respuesta.text
    assert 'Ana López' in respuesta.text
