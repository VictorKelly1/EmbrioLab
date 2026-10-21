import datetime
import getpass
import os
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.cuentas.models import Rol
from apps.cuentas.services import crear_usuario
from apps.personas.models import Genero
from apps.personas.services import crear_persona

CAMPOS = [
    ('correo', 'Correo'),
    ('nombre', 'Nombre'),
    ('apellido_paterno', 'Apellido paterno'),
    ('apellido_materno', 'Apellido materno (opcional)'),
    ('genero', 'Género (masculino/femenino)'),
    ('fecha_nacimiento', 'Fecha de nacimiento (AAAA-MM-DD)'),
    ('curp', 'CURP'),
    ('sueldo', 'Sueldo'),
]


class Command(BaseCommand):
    help = (
        'Crea un usuario con rol de administrador (y su persona). '
        'Los datos que falten se piden en la terminal; la contraseña también '
        'puede venir de la variable de entorno CREAR_ADMIN_PASSWORD.'
    )

    def add_arguments(self, parser):
        for campo, ayuda in CAMPOS:
            parser.add_argument(f'--{campo.replace("_", "-")}', dest=campo, help=ayuda)

    def handle(self, *args, **opciones):
        datos = {}
        for campo, etiqueta in CAMPOS:
            valor = opciones.get(campo)
            if valor is None:
                valor = input(f'{etiqueta}: ').strip()
            datos[campo] = valor

        password = os.environ.get('CREAR_ADMIN_PASSWORD') or self._pedir_password()

        try:
            fecha = datetime.date.fromisoformat(datos['fecha_nacimiento'])
            sueldo = Decimal(datos['sueldo'])
        except (ValueError, InvalidOperation) as error:
            raise CommandError(f'Dato inválido: {error}') from error
        if datos['genero'] not in Genero.values:
            raise CommandError('El género debe ser "masculino" o "femenino".')

        try:
            with transaction.atomic():
                persona = crear_persona(
                    nombre=datos['nombre'],
                    apellido_paterno=datos['apellido_paterno'],
                    apellido_materno=datos['apellido_materno'],
                    genero=datos['genero'],
                    fecha_nacimiento=fecha,
                    curp=datos['curp'],
                )
                usuario = crear_usuario(
                    persona=persona,
                    correo=datos['correo'],
                    password=password,
                    rol=Rol.ADMIN,
                    sueldo=sueldo,
                )
        except ValidationError as error:
            raise CommandError('; '.join(error.messages)) from error

        self.stdout.write(self.style.SUCCESS(f'Administrador creado: {usuario.correo}'))

    def _pedir_password(self):
        password = getpass.getpass('Contraseña: ')
        if password != getpass.getpass('Repita la contraseña: '):
            raise CommandError('Las contraseñas no coinciden.')
        return password
