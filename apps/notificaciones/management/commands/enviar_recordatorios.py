from django.core.management.base import BaseCommand

from apps.notificaciones.services import programar_recordatorios


class Command(BaseCommand):
    help = (
        'Encola el recordatorio de las citas que empiezan en las próximas 24 h. '
        'Pensado para correr cada pocos minutos (servicio `recordatorios` o cron).'
    )

    def handle(self, *args, **opciones):
        citas = programar_recordatorios()
        self.stdout.write(f'Recordatorios encolados: {citas}')
