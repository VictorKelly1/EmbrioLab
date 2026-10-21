from django.core.files.storage import FileSystemStorage


class AlmacenamientoPrivado(FileSystemStorage):
    """Archivos sin URL pública: solo se entregan desde una vista con control de rol."""

    def url(self, name):
        raise ValueError('Los archivos privados no tienen URL pública; sírvalos desde una vista.')
