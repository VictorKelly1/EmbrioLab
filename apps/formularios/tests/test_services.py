import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from apps.citas.services import TokenInvalido, generar_token_qr, obtener_cita_por_token
from apps.citas.tests.factories import CitaFactory
from apps.formularios.esquema import validar_esquema
from apps.formularios.models import Formulario, FormularioLlenado, VersionFormulario
from apps.formularios.selectors import respuestas_de, version_para
from apps.formularios.services import crear_formulario, guardar_respuestas, publicar_version
from apps.formularios.tests.factories import ESQUEMA_MINIMO, VersionFormularioFactory
from apps.pacientes.tests.factories import PacienteFactory

pytestmark = pytest.mark.django_db


# Migración de datos


def test_la_migracion_carga_los_dos_formularios_validos():
    formularios = Formulario.objects.filter(nombre__startswith='Formulario de la visita')
    assert {f.genero_aplicable for f in formularios} == {'masculino', 'femenino'}
    for formulario in formularios:
        version = formulario.versiones.get(publicada=True)
        validar_esquema(version.esquema)


def test_cada_genero_recibe_su_formulario():
    hombre = PacienteFactory(persona__genero='masculino')
    mujer = PacienteFactory(persona__genero='femenino')
    assert version_para(hombre).formulario.genero_aplicable == 'masculino'
    assert version_para(mujer).formulario.genero_aplicable == 'femenino'


# Versiones


def test_publicar_version_despublica_la_anterior():
    formulario = crear_formulario(nombre=' Prueba ')
    primera = publicar_version(formulario, ESQUEMA_MINIMO)
    segunda = publicar_version(formulario, ESQUEMA_MINIMO)

    primera.refresh_from_db()
    assert formulario.nombre == 'Prueba'
    assert (primera.numero_version, primera.publicada) == (1, False)
    assert (segunda.numero_version, segunda.publicada) == (2, True)


def test_publicar_valida_el_esquema():
    formulario = crear_formulario(nombre='Prueba')
    with pytest.raises(ValidationError):
        publicar_version(formulario, {'secciones': []})
    assert not formulario.versiones.exists()


def test_la_bd_permite_una_sola_version_publicada():
    version = VersionFormularioFactory()
    with pytest.raises(IntegrityError):
        VersionFormularioFactory(formulario=version.formulario, numero_version=2)


def test_formulario_especifico_gana_sobre_el_general():
    Formulario.objects.all().update(activo=False)
    general = VersionFormularioFactory(formulario__genero_aplicable='')
    paciente = PacienteFactory(persona__genero='femenino')
    assert version_para(paciente) == general

    especifico = VersionFormularioFactory(formulario__genero_aplicable='femenino')
    assert version_para(paciente) == especifico


def test_sin_formulario_disponible():
    Formulario.objects.all().update(activo=False)
    assert version_para(PacienteFactory()) is None


# Respuestas


def test_guardar_respuestas_consume_el_token():
    cita = CitaFactory()
    token = generar_token_qr(cita)
    version = VersionFormularioFactory()

    llenado = guardar_respuestas(cita, version, {'ayuno': True, 'horas': 8})

    assert llenado.respuestas == {'ayuno': True, 'horas': 8}
    with pytest.raises(TokenInvalido):
        obtener_cita_por_token(token)
    assert respuestas_de(llenado) == [
        {'seccion': 'Visita', 'etiqueta': '¿Viene en ayuno?', 'valor': 'Sí'},
        {'seccion': 'Visita', 'etiqueta': '¿Cuántas horas?', 'valor': 8},
    ]


def test_un_solo_formulario_por_cita():
    cita = CitaFactory()
    version = VersionFormularioFactory()
    guardar_respuestas(cita, version, {})
    with pytest.raises(ValidationError):
        guardar_respuestas(cita, version, {})
    assert FormularioLlenado.objects.count() == 1


def test_las_versiones_con_respuestas_no_se_borran():
    version = VersionFormularioFactory()
    guardar_respuestas(CitaFactory(), version, {})
    with pytest.raises(IntegrityError):
        VersionFormulario.objects.filter(pk=version.pk).delete()
