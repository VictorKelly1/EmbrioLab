import datetime
import re

import pytest
from django.core import mail
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.utils import timezone

from apps.citas.models import EstadoCita
from apps.citas.services import obtener_cita_por_token, reprogramar_cita
from apps.citas.tests.factories import CitaFactory, en
from apps.formularios.tests.factories import FormularioLlenadoFactory
from apps.notificaciones.models import EstadoNotificacion, Notificacion, TipoNotificacion
from apps.notificaciones.services import (
    citas_por_recordar,
    destinatarios,
    enviar_link_formulario,
    enviar_recordatorio,
    programar_recordatorios,
)
from apps.notificaciones.tests.utils import CORREO, WHATSAPP, con_contactos

pytestmark = pytest.mark.django_db


def _cita(**extra):
    cita = CitaFactory(**extra)
    con_contactos(cita.paciente.persona)
    return cita


def _token(texto: str) -> str:
    return re.search(r'/f/([\w-]+)/', texto).group(1)


# Destinatarios


def test_destinatarios_son_los_contactos_principales():
    persona = con_contactos(CitaFactory().paciente.persona)
    assert destinatarios(persona) == {'correo': CORREO, 'whatsapp': WHATSAPP}


def test_solo_los_canales_con_contacto():
    persona = con_contactos(CitaFactory().paciente.persona, whatsapp='')
    assert destinatarios(persona) == {'correo': CORREO}


# Link del formulario


def test_link_crea_una_notificacion_pendiente_por_canal():
    cita = _cita()
    filas = enviar_link_formulario(cita)
    assert {(n.canal, n.destinatario) for n in filas} == {
        ('correo', CORREO),
        ('whatsapp', WHATSAPP),
    }
    assert all(n.tipo == 'qr' and n.estado == 'pendiente' and n.cita == cita for n in filas)


def test_nada_sale_antes_de_confirmar_la_transaccion(django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        enviar_link_formulario(_cita())
    assert len(callbacks) == 1
    assert mail.outbox == []


def test_el_link_enviado_abre_el_formulario_de_la_cita(django_capture_on_commit_callbacks):
    cita = _cita()
    with django_capture_on_commit_callbacks(execute=True):
        enviar_link_formulario(cita)
    assert len(mail.outbox) == 1
    correo = mail.outbox[0]
    assert correo.to == [CORREO]
    assert 'http://localhost:8000/f/' in correo.body
    assert obtener_cita_por_token(_token(correo.body)) == cita
    assert set(Notificacion.objects.values_list('estado', flat=True)) == {'enviado'}


def test_el_mensaje_no_lleva_datos_del_paciente_salvo_su_nombre(
    django_capture_on_commit_callbacks,
):
    cita = _cita()
    persona = cita.paciente.persona
    with django_capture_on_commit_callbacks(execute=True):
        enviar_link_formulario(cita)
    cuerpo = mail.outbox[0].body
    assert persona.nombre in cuerpo
    assert persona.curp not in cuerpo
    assert persona.apellido_paterno not in cuerpo


def test_link_exige_un_contacto():
    with pytest.raises(ValidationError, match='no tiene correo ni WhatsApp'):
        enviar_link_formulario(CitaFactory())


def test_link_no_para_una_cita_no_atendida():
    with pytest.raises(ValidationError, match='no fue atendida'):
        enviar_link_formulario(_cita(estado=EstadoCita.NO_ATENDIDA))


def test_link_no_si_ya_lleno_el_formulario():
    cita = _cita()
    FormularioLlenadoFactory(cita=cita)
    with pytest.raises(ValidationError, match='ya llenó el formulario'):
        enviar_link_formulario(cita)


# Recordatorios


def test_citas_por_recordar_son_las_programadas_de_las_proximas_24_h():
    ahora = timezone.now()
    dentro = CitaFactory(fecha_hora=ahora + datetime.timedelta(hours=23))
    CitaFactory(fecha_hora=ahora + datetime.timedelta(hours=25))
    CitaFactory(fecha_hora=ahora - datetime.timedelta(hours=1))
    CitaFactory(fecha_hora=ahora + datetime.timedelta(hours=2), recordatorio_enviado=True)
    CitaFactory(fecha_hora=ahora + datetime.timedelta(hours=3), estado=EstadoCita.ATENDIDA)
    assert list(citas_por_recordar(ahora)) == [dentro]


def test_recordatorio_marca_la_cita(django_capture_on_commit_callbacks):
    cita = _cita(fecha_hora=en(1))
    with django_capture_on_commit_callbacks(execute=True):
        filas = enviar_recordatorio(cita)
    cita.refresh_from_db()
    assert cita.recordatorio_enviado
    assert {n.tipo for n in filas} == {TipoNotificacion.RECORDATORIO}
    correo = mail.outbox[0]
    assert correo.subject == 'Recordatorio de su cita en EmbrioLab'
    assert obtener_cita_por_token(_token(correo.body)) == cita


def test_recordatorio_no_se_repite():
    cita = _cita(fecha_hora=en(1))
    enviar_recordatorio(cita)
    assert enviar_recordatorio(cita) == []
    assert Notificacion.objects.count() == 2  # correo y WhatsApp, una sola vez


def test_sin_contactos_la_cita_queda_sin_recordatorio():
    cita = CitaFactory(fecha_hora=en(1))
    assert enviar_recordatorio(cita) == []
    cita.refresh_from_db()
    assert not cita.recordatorio_enviado


def test_recordatorio_sin_link_si_ya_lleno_el_formulario(django_capture_on_commit_callbacks):
    cita = _cita(fecha_hora=en(1))
    FormularioLlenadoFactory(cita=cita)
    with django_capture_on_commit_callbacks(execute=True):
        enviar_recordatorio(cita)
    assert '/f/' not in mail.outbox[0].body
    assert Notificacion.objects.filter(estado=EstadoNotificacion.ENVIADO).count() == 2


def test_reprogramar_vuelve_a_programar_el_recordatorio():
    cita = _cita(fecha_hora=timezone.now() + datetime.timedelta(hours=5))
    enviar_recordatorio(cita)
    cita.refresh_from_db()
    reprogramar_cita(cita, fecha_hora=en(5))
    cita.refresh_from_db()
    assert not cita.recordatorio_enviado


def test_programar_recordatorios_cuenta_las_citas():
    ahora = timezone.now()
    _cita(fecha_hora=ahora + datetime.timedelta(hours=3))
    _cita(fecha_hora=ahora + datetime.timedelta(hours=4))
    CitaFactory(fecha_hora=ahora + datetime.timedelta(hours=5))  # sin contactos
    assert programar_recordatorios(ahora) == 2


def test_comando_enviar_recordatorios(capsys):
    _cita(fecha_hora=timezone.now() + datetime.timedelta(hours=3))
    call_command('enviar_recordatorios')
    assert 'Recordatorios encolados: 1' in capsys.readouterr().out
