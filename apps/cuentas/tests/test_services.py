import datetime
from decimal import Decimal

import pytest
from django.contrib.auth import authenticate
from django.core.exceptions import ValidationError
from django.test import RequestFactory

from apps.cuentas.models import Rol
from apps.cuentas.services import crear_usuario, registrar_usuario
from apps.personas.models import Persona
from apps.personas.tests.factories import PersonaFactory

pytestmark = pytest.mark.django_db


def _crear(**extra):
    datos = {
        'persona': PersonaFactory(),
        'correo': 'Recepcion@EmbrioLab.test',
        'password': 'una-clave-segura-987',
        'rol': Rol.RECEPCIONISTA,
        'sueldo': Decimal('12000.00'),
    }
    return crear_usuario(**{**datos, **extra})


def test_crea_usuario_con_un_rol():
    usuario = _crear()
    assert usuario.correo == 'recepcion@embriolab.test'
    assert usuario.roles == {Rol.RECEPCIONISTA}
    assert usuario.tiene_rol(Rol.RECEPCIONISTA)
    assert not usuario.tiene_rol(Rol.QUIMICO, Rol.ADMIN)
    assert usuario.check_password('una-clave-segura-987')


def test_login_con_correo_sin_importar_mayusculas():
    usuario = _crear()
    request = RequestFactory().post('/entrar/')
    autenticado = authenticate(
        request, username='RECEPCION@embriolab.test', password='una-clave-segura-987'
    )
    assert autenticado == usuario


def test_correo_unico_sin_importar_mayusculas():
    _crear()
    with pytest.raises(ValidationError):
        _crear(correo='recepcion@embriolab.TEST')


def test_quimico_requiere_cedula():
    with pytest.raises(ValidationError) as error:
        _crear(rol=Rol.QUIMICO)
    assert 'cedula_profesional' in error.value.message_dict


def test_crea_quimico():
    usuario = _crear(rol=Rol.QUIMICO, cedula_profesional='12345678')
    assert usuario.quimico.cedula_profesional == '12345678'
    assert usuario.roles == {Rol.QUIMICO}


def test_rol_desconocido():
    with pytest.raises(ValidationError):
        _crear(rol='doctor')


def test_usuario_inactivo_no_tiene_roles_efectivos():
    usuario = _crear()
    usuario.is_active = False
    assert not usuario.tiene_rol(Rol.RECEPCIONISTA)


def test_color_invalido():
    with pytest.raises(ValidationError) as error:
        _crear(color='azul')
    assert 'color' in error.value.message_dict


def test_password_se_guarda_con_argon2():
    assert _crear().password.startswith('argon2')


def test_rechaza_password_debil():
    with pytest.raises(ValidationError) as error:
        _crear(password='12345678')
    assert 'password' in error.value.message_dict


def test_registrar_usuario_crea_persona_y_usuario():
    usuario = registrar_usuario(
        datos_persona={
            'nombre': 'Rosa',
            'apellido_paterno': 'Quiroz',
            'genero': 'femenino',
            'fecha_nacimiento': datetime.date(1990, 1, 1),
            'curp': 'QUXR900101MJCRSS01',
        },
        correo='rosa@embriolab.test',
        password='una-clave-segura-987',
        rol=Rol.QUIMICO,
        sueldo=Decimal('15000'),
        cedula_profesional='12345678',
    )
    assert usuario.roles == {Rol.QUIMICO}
    assert usuario.persona.nombre_completo == 'Rosa Quiroz'


def test_registrar_usuario_no_deja_persona_si_falla():
    with pytest.raises(ValidationError):
        registrar_usuario(
            datos_persona={
                'nombre': 'Rosa',
                'apellido_paterno': 'Quiroz',
                'genero': 'femenino',
                'fecha_nacimiento': datetime.date(1990, 1, 1),
                'curp': 'QUXR900101MJCRSS01',
            },
            correo='rosa@embriolab.test',
            password='una-clave-segura-987',
            rol=Rol.QUIMICO,
            sueldo=Decimal('15000'),
        )
    assert not Persona.objects.exists()
