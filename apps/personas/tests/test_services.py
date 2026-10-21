import datetime

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from apps.personas.models import Contacto, Direccion, Genero, Persona, TipoContacto
from apps.personas.selectors import contactos_principales
from apps.personas.services import (
    actualizar_persona,
    crear_persona,
    guardar_contactos_principales,
    guardar_direccion,
)

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


def test_nombre_busqueda_se_calcula_al_guardar():
    persona = crear_persona(**{**DATOS, 'nombre': 'José María'})
    assert persona.nombre_busqueda == 'jose maria lopez garcia'

    persona.apellido_materno = 'Núñez'
    persona.save(update_fields=['apellido_materno'])
    persona.refresh_from_db()
    assert persona.nombre_busqueda == 'jose maria lopez nunez'


# actualizar_persona


def test_actualizar_persona():
    persona = crear_persona(**DATOS)

    actualizar_persona(persona, nombre=' Ana Sofía ', curp='loga920517mjclrn01')

    persona.refresh_from_db()
    assert persona.nombre == 'Ana Sofía'
    assert persona.curp == 'LOGA920517MJCLRN01'
    assert persona.nombre_busqueda == 'ana sofia lopez garcia'


def test_actualizar_persona_respeta_curp_unica():
    otra = crear_persona(**DATOS)
    persona = crear_persona(**{**DATOS, 'curp': 'LOGA920517MJCLRN01'})
    with pytest.raises(ValidationError) as error:
        actualizar_persona(persona, curp=otra.curp)
    assert 'curp' in error.value.message_dict


def test_actualizar_persona_rechaza_campos_no_editables():
    persona = crear_persona(**DATOS)
    with pytest.raises(ValueError):
        actualizar_persona(persona, nombre_busqueda='x')


def test_foto_privada_con_nombre_aleatorio(imagen_png):
    persona = crear_persona(**DATOS, foto=imagen_png)

    assert persona.foto.name.startswith('fotos/')
    assert 'Ana' not in persona.foto.name
    assert persona.foto.storage.exists(persona.foto.name)
    with pytest.raises(ValueError):
        persona.foto.url  # noqa: B018  sin URL pública


def test_reemplazar_y_quitar_foto_borra_el_archivo_anterior(
    imagen_png, django_capture_on_commit_callbacks
):
    persona = crear_persona(**DATOS, foto=imagen_png)
    primera = persona.foto.name
    imagen_png.seek(0)

    with django_capture_on_commit_callbacks(execute=True):
        actualizar_persona(persona, foto=imagen_png)
    segunda = persona.foto.name
    assert segunda != primera
    assert not persona.foto.storage.exists(primera)

    almacenamiento = persona.foto.storage
    with django_capture_on_commit_callbacks(execute=True):
        actualizar_persona(persona, foto=False)
    assert not persona.foto
    assert not almacenamiento.exists(segunda)


# guardar_direccion

DIRECCION = {
    'calle': 'Av. Juárez',
    'numero': '123',
    'colonia_frac': 'Centro',
    'ciudad': 'Guadalajara',
    'estado': 'Jalisco',
    'codigo_postal': '44100',
}


def test_guardar_direccion_crea_y_luego_actualiza():
    persona = crear_persona(**DATOS)

    direccion = guardar_direccion(persona, DIRECCION)
    assert persona.direccion == direccion
    assert direccion.pais == 'México'

    misma = guardar_direccion(persona, {**DIRECCION, 'numero': '456'})
    assert misma.pk == direccion.pk
    assert Direccion.objects.count() == 1


def test_direccion_compartida_no_se_modifica():
    persona = crear_persona(**DATOS)
    compartida = guardar_direccion(persona, DIRECCION)
    pareja = crear_persona(**{**DATOS, 'curp': 'LOGA920517MJCLRN01'}, direccion=compartida)

    nueva = guardar_direccion(persona, {**DIRECCION, 'numero': '456'})

    assert nueva.pk != compartida.pk
    pareja.refresh_from_db()
    assert pareja.direccion.numero == '123'


def test_direccion_vacia_deja_a_la_persona_sin_direccion():
    persona = crear_persona(**DATOS)
    guardar_direccion(persona, DIRECCION)

    assert guardar_direccion(persona, {'pais': 'México', 'calle': '  '}) is None
    persona.refresh_from_db()
    assert persona.direccion is None


# guardar_contactos_principales


def test_guardar_contactos_normaliza():
    persona = crear_persona(**DATOS)

    guardar_contactos_principales(
        persona,
        {
            TipoContacto.TELEFONO: '(33) 1234-5678',
            TipoContacto.CORREO: ' Ana@Correo.MX ',
            TipoContacto.WHATSAPP: '',
        },
    )

    assert contactos_principales(persona) == {
        'telefono': '3312345678',
        'correo': 'ana@correo.mx',
    }


def test_cambiar_y_quitar_contacto():
    persona = crear_persona(**DATOS)
    guardar_contactos_principales(persona, {TipoContacto.TELEFONO: '3312345678'})

    guardar_contactos_principales(persona, {TipoContacto.TELEFONO: '3399999999'})
    assert persona.contactos.get().valor == '3399999999'

    guardar_contactos_principales(persona, {TipoContacto.TELEFONO: ''})
    assert not persona.contactos.exists()


def test_contacto_invalido():
    persona = crear_persona(**DATOS)
    with pytest.raises(ValidationError) as error:
        guardar_contactos_principales(
            persona, {TipoContacto.CORREO: 'no-es-correo', TipoContacto.WHATSAPP: '123'}
        )
    assert set(error.value.message_dict) == {'correo', 'whatsapp'}


def test_la_bd_permite_un_solo_principal_por_tipo():
    persona = crear_persona(**DATOS)
    Contacto.objects.create(persona=persona, tipo='telefono', valor='3311111111', principal=True)
    with pytest.raises(IntegrityError):
        Contacto.objects.create(
            persona=persona, tipo='telefono', valor='3322222222', principal=True
        )
