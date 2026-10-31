"""
Tareas del worker (`manage.py db_worker`). Reciben ids y no objetos: la tarea se guarda
en la BD como JSON y se ejecuta en otro proceso.
"""

import datetime

from django.conf import settings
from django.tasks import task
from django.utils import timezone

from apps.notificaciones import envio


@task
def enviar_notificaciones(ids: list[int], intento: int = 1) -> None:
    pendientes = envio.procesar(ids)
    if pendientes and intento <= len(settings.NOTIFICACIONES_REINTENTOS):
        espera = datetime.timedelta(minutes=settings.NOTIFICACIONES_REINTENTOS[intento - 1])
        encolar(pendientes, intento=intento + 1, espera=espera)


def encolar(ids: list[int], *, intento: int = 1, espera: datetime.timedelta | None = None):
    tarea = enviar_notificaciones
    if espera and tarea.get_backend().supports_defer:
        tarea = tarea.using(run_after=timezone.now() + espera)
    return tarea.enqueue(ids, intento=intento)
