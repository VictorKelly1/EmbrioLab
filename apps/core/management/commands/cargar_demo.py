from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.core.demo import borrar_datos, cargar_datos


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

    def handle(self, *args, confirmar=False, solo_borrar=False, **opciones):
        if not settings.DEBUG:
            raise CommandError('Solo se usa en desarrollo (DEBUG=True). Nunca en producción.')
        if not confirmar:
            raise CommandError(
                'Esto BORRA los datos de pacientes, citas y pedidos. '
                'Si está seguro, repita con --confirmar.'
            )
        try:
            with transaction.atomic():
                borrados = borrar_datos()
                creados = {} if solo_borrar else cargar_datos()
        except ValueError as error:
            raise CommandError(str(error)) from error
        self.stdout.write('Borrado: ' + _resumen(borrados))
        if creados:
            self.stdout.write(self.style.SUCCESS('Datos de ejemplo: ' + _resumen(creados)))


def _resumen(conteos: dict[str, int]) -> str:
    return ', '.join(f'{nombre} {cuantos}' for nombre, cuantos in conteos.items()) or 'nada'
