import pytest
from django.core.management import CommandError, call_command

from apps.cuentas.models import Rol, Usuario

pytestmark = pytest.mark.django_db

DATOS = {
    'correo': 'admin@embriolab.test',
    'nombre': 'Laura',
    'apellido_paterno': 'Medina',
    'apellido_materno': 'Ruiz',
    'genero': 'femenino',
    'fecha_nacimiento': '1985-03-02',
    'curp': 'MERL850302MJCDZR04',
    'sueldo': '20000',
}


@pytest.fixture(autouse=True)
def password(monkeypatch):
    monkeypatch.setenv('CREAR_ADMIN_PASSWORD', 'admin-clave-segura-555')


def test_crear_admin():
    call_command('crear_admin', **DATOS)

    usuario = Usuario.objects.get(correo='admin@embriolab.test')
    assert usuario.roles == {Rol.ADMIN}
    assert usuario.persona.curp == 'MERL850302MJCDZR04'
    assert usuario.check_password('admin-clave-segura-555')


def test_crear_admin_con_datos_invalidos_no_deja_nada_a_medias():
    with pytest.raises(CommandError):
        call_command('crear_admin', **{**DATOS, 'curp': 'INVALIDA'})
    with pytest.raises(CommandError):
        call_command('crear_admin', **{**DATOS, 'genero': 'otro'})
    assert not Usuario.objects.exists()
