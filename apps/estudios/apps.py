from django.apps import AppConfig


class EstudiosConfig(AppConfig):
    name = 'apps.estudios'
    label = 'estudios'

    def ready(self):
        from apps.estudios import checks  # noqa: F401  (registra el system check)
