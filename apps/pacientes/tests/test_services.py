import datetime
import importlib

import pytest
from django.apps import apps as django_apps
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from apps.core.models import BorradoFisicoNoPermitido
from apps.core.services import dar_de_baja
from apps.pacientes.models import Doctor, Paciente
from apps.pacientes.services import (
    actualizar_doctor,
    actualizar_paciente,
    crear_doctor,
    registrar_paciente,
)
from apps.personas.models import Genero, Persona
from apps.personas.selectors import contactos_principales

pytestmark = pytest.mark.django_db

PERSONA = {
    'nombre': 'Ana',
    'apellido_paterno': 'López',
    'apellido_materno': 'García',
    'genero': Genero.FEMENINO,
    'fecha_nacimiento': datetime.date(1992, 5, 17),
    'curp': 'LOGA920517MJCLRN09',
}


def _registrar(**cambios):
    return registrar_paciente(
        datos_persona={**PERSONA, **cambios},
        contactos={'whatsapp': '33 1234 5678', 'correo': 'ana@correo.mx'},
        direccion={
            'calle': 'Juárez',
            'numero': '1',
            'colonia_frac': 'Centro',
            'ciudad': 'Guadalajara',
            'estado': 'Jalisco',
            'codigo_postal': '44100',
        },
    )


def test_registrar_paciente():
    paciente = _registrar()

    assert paciente.estado_actividad is True
    assert paciente.persona.curp == PERSONA['curp']
    assert paciente.folio == f'LOGA{paciente.numero}'
    assert paciente.persona.direccion.ciudad == 'Guadalajara'
    assert contactos_principales(paciente.persona) == {
        'whatsapp': '3312345678',
        'correo': 'ana@correo.mx',
    }


def test_numeros_consecutivos_y_unicos():
    primero = _registrar()
    segundo = _registrar(curp='LOGA920517MJCLRN01')
    assert segundo.numero == primero.numero + 1


def test_no_se_registra_dos_veces():
    paciente = _registrar()
    with pytest.raises(ValidationError) as error:
        _registrar(curp=PERSONA['curp'].lower())
    assert f'número {paciente.numero}' in error.value.message_dict['curp'][0]
    assert Paciente.objects.count() == 1


def test_error_no_deja_registros_a_medias():
    with pytest.raises(ValidationError):
        registrar_paciente(datos_persona=PERSONA, contactos={'correo': 'no-es-correo'})
    assert not Persona.objects.exists()
    assert not Paciente.objects.exists()


def test_actualizar_paciente():
    paciente = _registrar()

    actualizar_paciente(
        paciente,
        datos_persona={**PERSONA, 'apellido_materno': 'Ruiz'},
        contactos={'whatsapp': '', 'correo': 'ana@correo.mx', 'telefono': '3311111111'},
        direccion=None,
    )

    paciente.persona.refresh_from_db()
    assert paciente.folio == f'LORU{paciente.numero}'
    assert paciente.persona.direccion is None
    assert contactos_principales(paciente.persona) == {
        'correo': 'ana@correo.mx',
        'telefono': '3311111111',
    }


@pytest.mark.parametrize(
    'contactos', [None, {}, {'telefono': '3311111111'}, {'correo': ' ', 'whatsapp': ''}]
)
def test_registrar_exige_correo_o_whatsapp(contactos):
    with pytest.raises(ValidationError) as error:
        registrar_paciente(datos_persona=PERSONA, contactos=contactos)
    assert set(error.value.message_dict) == {'correo', 'whatsapp'}
    assert not Persona.objects.exists()


@pytest.mark.parametrize('contactos', [{'correo': 'ana@correo.mx'}, {'whatsapp': '3312345678'}])
def test_basta_un_correo_o_un_whatsapp(contactos):
    paciente = registrar_paciente(datos_persona=PERSONA, contactos=contactos)
    assert contactos_principales(paciente.persona) == contactos


def test_al_editar_no_se_puede_quitar_todo_el_contacto():
    paciente = _registrar()
    with pytest.raises(ValidationError):
        actualizar_paciente(
            paciente, datos_persona=PERSONA, contactos={'correo': '', 'whatsapp': ''}
        )
    # Lo que no se toca cuenta: quitar solo el WhatsApp deja el correo.
    actualizar_paciente(paciente, datos_persona=PERSONA, contactos={'whatsapp': ''})
    assert contactos_principales(paciente.persona) == {'correo': 'ana@correo.mx'}


def test_paciente_viejo_sin_contacto_debe_agregarlo_al_editar():
    paciente = _registrar()
    paciente.persona.contactos.all().delete()
    with pytest.raises(ValidationError):
        actualizar_paciente(paciente, datos_persona=PERSONA)
    actualizar_paciente(paciente, datos_persona=PERSONA, contactos={'correo': 'ana@correo.mx'})


def test_baja_logica_sin_borrado_fisico():
    paciente = _registrar()
    dar_de_baja(paciente)
    assert Paciente.objects.inactivos().get() == paciente
    with pytest.raises(BorradoFisicoNoPermitido):
        paciente.delete()


def test_la_bd_exige_numero_unico():
    paciente = _registrar()
    otra = _registrar(curp='LOGA920517MJCLRN01').persona
    with pytest.raises(IntegrityError):
        Paciente.objects.create(persona=otra, numero=paciente.numero)


# Doctores


def test_crear_y_actualizar_doctor():
    doctor = crear_doctor(
        nombre='  Dr.  Juan   Pérez ',
        correo=' Juan@Consultorio.MX ',
        whatsapp=' 3312345678 ',
        contacto=' Consultorio 4, Torre Médica ',
    )
    assert doctor.nombre == 'Dr. Juan Pérez'
    assert (doctor.correo, doctor.whatsapp) == ('juan@consultorio.mx', '3312345678')
    assert doctor.contacto == 'Consultorio 4, Torre Médica'

    actualizar_doctor(doctor, nombre='Dra. Laura Gómez', whatsapp='3311112222')
    guardado = Doctor.objects.get()
    assert guardado.nombre == 'Dra. Laura Gómez'
    assert (guardado.correo, guardado.whatsapp, guardado.contacto) == ('', '3311112222', '')


@pytest.mark.parametrize(
    'contacto', [{}, {'correo': '  ', 'whatsapp': ''}, {'contacto': 'Tel. 33'}]
)
def test_doctor_requiere_correo_o_whatsapp(contacto):
    with pytest.raises(ValidationError) as error:
        crear_doctor(nombre='Dr. Juan', **contacto)
    assert set(error.value.message_dict) == {'correo', 'whatsapp'}
    assert not Doctor.objects.exists()


def test_no_se_le_puede_quitar_todo_el_contacto_al_doctor():
    doctor = crear_doctor(nombre='Dr. Juan', correo='juan@example.com')
    with pytest.raises(ValidationError):
        actualizar_doctor(doctor, nombre='Dr. Juan')
    doctor.refresh_from_db()
    assert doctor.correo == 'juan@example.com'


@pytest.mark.parametrize(
    ('campo', 'valor'), [('correo', 'no-es-correo'), ('whatsapp', '12-34'), ('whatsapp', '123')]
)
def test_doctor_con_contacto_invalido(campo, valor):
    with pytest.raises(ValidationError) as error:
        crear_doctor(nombre='Dr. Juan', **{campo: valor})
    assert campo in error.value.message_dict


@pytest.mark.parametrize(
    ('contacto', 'esperado'),
    [
        ('Juan@Example.com', ('juan@example.com', '', '')),
        ('33 1234-5678', ('', '3312345678', '')),
        ('(33) 1234 5678', ('', '3312345678', '')),
        ('Consultorio 4, tel. 3312345678', ('', '', 'Consultorio 4, tel. 3312345678')),
    ],
)
def test_migracion_separa_el_contacto_del_doctor(contacto, esperado):
    migracion = importlib.import_module('apps.pacientes.migrations.0003_separar_contacto_doctor')
    doctor = Doctor.objects.create(nombre='Dr. Juan', contacto=contacto)
    migracion.separar(django_apps, None)
    doctor.refresh_from_db()
    assert (doctor.correo, doctor.whatsapp, doctor.contacto) == esperado
    migracion.juntar(django_apps, None)
    doctor.refresh_from_db()
    assert doctor.contacto == next(d for d in esperado if d)


def test_doctor_requiere_nombre():
    with pytest.raises(ValidationError):
        crear_doctor(nombre='   ', correo='juan@example.com')
