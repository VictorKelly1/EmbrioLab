from django.core.management.base import BaseCommand

from apps.core.limites import limpiar_vencidos


class Command(BaseCommand):
    help = 'Borra los contadores de intentos de más de un día. Pensado para correr con cron.'

    def handle(self, *args, **opciones):
        borrados = limpiar_vencidos()
        self.stdout.write(f'Contadores borrados: {borrados}')
