import datetime

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from apps.personas.models import Genero, Persona
from apps.personas.services import crear_persona

pytestmark = pytest.mark.django_db

DATOS = {
    'nombre': ' Ana ',
    'apellido_paterno': 'López',
    'apellido_materno': 'García',
    'genero': Genero.FEMENINO,
    'fecha_nacimiento': datetime.date(1992, 5, 17),
    'curp': 'logA920517mjclrn09',
}


def test_crear_persona_normaliza_datos():
    persona = crear_persona(**DATOS)
    assert persona.nombre == 'Ana'
    assert persona.curp == 'LOGA920517MJCLRN09'
    assert persona.nombre_completo == 'Ana López García'


def test_sin_apellido_materno():
    persona = crear_persona(**{**DATOS, 'apellido_materno': ''})
    assert persona.nombre_completo == 'Ana López'


def test_curp_unica():
    crear_persona(**DATOS)
    with pytest.raises(ValidationError) as error:
        crear_persona(**DATOS)
    assert 'curp' in error.value.message_dict


def test_curp_invalida():
    with pytest.raises(ValidationError) as error:
        crear_persona(**{**DATOS, 'curp': 'NO-ES-CURP'})
    assert 'curp' in error.value.message_dict


def test_la_bd_rechaza_curp_invalida_aunque_se_salte_el_servicio():
    with pytest.raises(IntegrityError):
        Persona.objects.create(**{**DATOS, 'curp': 'XXXX'})
