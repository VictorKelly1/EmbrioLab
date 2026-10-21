import datetime

import pytest
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
    doctor = crear_doctor(nombre='  Dr.  Juan   Pérez ', contacto=' 3312345678 ')
    assert doctor.nombre == 'Dr. Juan Pérez'
    assert doctor.contacto == '3312345678'

    actualizar_doctor(doctor, nombre='Dra. Laura Gómez')
    assert Doctor.objects.get().nombre == 'Dra. Laura Gómez'
    assert Doctor.objects.get().contacto == ''


def test_doctor_requiere_nombre():
    with pytest.raises(ValidationError):
        crear_doctor(nombre='   ')
