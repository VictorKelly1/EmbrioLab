import os
import secrets

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.core.demo import USUARIOS, borrar_datos, cargar_datos, crear_usuarios


class Command(BaseCommand):
    help = (
        'SOLO DESARROLLO. Borra pacientes, doctores, citas, pedidos, formularios llenados y '
        'notificaciones, y carga datos de ejemplo. Conserva los usuarios, el catálogo de '
        'estudios y los formularios de las migraciones.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--confirmar',
            action='store_true',
            help='Sin esta opción no se borra nada.',
        )
        parser.add_argument(
            '--solo-borrar', action='store_true', help='Borra y no carga datos de ejemplo.'
        )
        parser.add_argument(
            '--con-usuarios',
            action='store_true',
            help=(
                'Crea antes los usuarios de ejemplo que falten (admin, recepción y dos '
                'químicos @embriolab.local). Contraseña: DEMO_PASSWORD o una al azar.'
            ),
        )

    def handle(self, *args, confirmar=False, solo_borrar=False, con_usuarios=False, **opciones):
        if not settings.DEBUG:
            raise CommandError('Solo se usa en desarrollo (DEBUG=True). Nunca en producción.')
        if not confirmar:
            raise CommandError(
                'Esto BORRA los datos de pacientes, citas y pedidos. '
                'Si está seguro, repita con --confirmar.'
            )
        password = os.environ.get('DEMO_PASSWORD') or secrets.token_urlsafe(12)
        usuarios = []
        try:
            with transaction.atomic():
                if con_usuarios:
                    usuarios = crear_usuarios(password)
                borrados = borrar_datos()
                creados = {} if solo_borrar else cargar_datos()
        except ValueError as error:
            raise CommandError(str(error)) from error
        except ValidationError as error:
            raise CommandError('; '.join(error.messages)) from error
        if usuarios:
            self.stdout.write(
                self.style.SUCCESS(f'Usuarios creados (contraseña: {password}): ')
                + ', '.join(usuarios)
            )
        elif con_usuarios:
            self.stdout.write(
                'Los usuarios de ejemplo ya existían: '
                + ', '.join(u[0] for u in USUARIOS)
                + ' (conservan su contraseña).'
            )
        self.stdout.write('Borrado: ' + _resumen(borrados))
        if creados:
            self.stdout.write(self.style.SUCCESS('Datos de ejemplo: ' + _resumen(creados)))


def _resumen(conteos: dict[str, int]) -> str:
    return ', '.join(f'{nombre} {cuantos}' for nombre, cuantos in conteos.items()) or 'nada'
