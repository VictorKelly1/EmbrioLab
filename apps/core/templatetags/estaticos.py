from pathlib import Path

from django import template
from django.conf import settings
from django.contrib.staticfiles import finders
from django.templatetags.static import static

register = template.Library()


@register.simple_tag
def estatico(ruta: str) -> str:
    """
    Como {% static %}, pero en desarrollo agrega ?v=<fecha de modificación> para que el
    navegador no use una versión vieja del CSS o JS. En producción los nombres ya llevan
    hash (ManifestStaticFilesStorage).
    """
    url = static(ruta)
    if settings.DEBUG:
        archivo = finders.find(ruta)
        if archivo:
            url = f'{url}?v={int(Path(archivo).stat().st_mtime)}'
    return url
