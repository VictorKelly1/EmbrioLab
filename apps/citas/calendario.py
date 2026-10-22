"""Arma la rejilla del calendario (días × bloques de 30 min). Solo presentación."""

import datetime
from dataclasses import dataclass, field

from django.conf import settings
from django.utils import timezone

from apps.citas.models import Cita

BLOQUE = datetime.timedelta(minutes=30)


class Vista:
    DIA = 'dia'
    SEMANA = 'semana'


@dataclass
class Celda:
    inicio: datetime.datetime
    citas: list[Cita] = field(default_factory=list)

    @property
    def pasada(self) -> bool:
        return self.inicio < timezone.now()


@dataclass
class Fila:
    hora: datetime.time
    celdas: list[Celda]


def _hora(texto: str) -> datetime.time:
    return datetime.time.fromisoformat(texto)


def dias_de(
    fecha: datetime.date, vista: str, con_citas: set[datetime.date] = frozenset()
) -> list[datetime.date]:
    """
    Días que se muestran. En la semana: los hábiles, más el día elegido y los días no
    hábiles que tengan citas (para que ninguna cita quede oculta).
    """
    if vista == Vista.DIA:
        return [fecha]
    lunes = fecha - datetime.timedelta(days=fecha.weekday())
    semana = [lunes + datetime.timedelta(days=d) for d in range(7)]
    return [
        dia
        for dia in semana
        if dia.weekday() in settings.CITAS_DIAS_HABILES or dia == fecha or dia in con_citas
    ]


def semana_completa(fecha: datetime.date) -> list[datetime.date]:
    lunes = fecha - datetime.timedelta(days=fecha.weekday())
    return [lunes, lunes + datetime.timedelta(days=6)]


def rango(dias: list[datetime.date]) -> tuple[datetime.datetime, datetime.datetime]:
    inicio = timezone.make_aware(datetime.datetime.combine(dias[0], datetime.time.min))
    fin = timezone.make_aware(datetime.datetime.combine(dias[-1], datetime.time.min))
    return inicio, fin + datetime.timedelta(days=1)


def _bloque_de(momento: datetime.datetime) -> datetime.time:
    local = timezone.localtime(momento)
    return datetime.time(local.hour, 0 if local.minute < 30 else 30)


def armar_filas(dias: list[datetime.date], citas: list[Cita]) -> list[Fila]:
    """
    Una fila por bloque del horario de atención. Si hay citas fuera de él (por ejemplo,
    una sin cita en la tarde), el horario se extiende para mostrarlas.
    """
    primera, ultima = _hora(settings.CITAS_HORA_INICIO), _hora(settings.CITAS_HORA_FIN)
    bloques_con_citas = [_bloque_de(c.fecha_hora) for c in citas]
    if bloques_con_citas:
        primera = min(primera, *bloques_con_citas)
        ultima = max(
            ultima,
            *[(datetime.datetime.combine(dias[0], b) + BLOQUE).time() for b in bloques_con_citas],
        )

    por_celda: dict[tuple[datetime.date, datetime.time], list[Cita]] = {}
    for cita in citas:
        clave = (timezone.localtime(cita.fecha_hora).date(), _bloque_de(cita.fecha_hora))
        por_celda.setdefault(clave, []).append(cita)

    filas = []
    actual = datetime.datetime.combine(dias[0], primera)
    fin = datetime.datetime.combine(dias[0], ultima)
    while actual < fin:
        hora = actual.time()
        filas.append(
            Fila(
                hora=hora,
                celdas=[
                    Celda(
                        inicio=timezone.make_aware(datetime.datetime.combine(dia, hora)),
                        citas=por_celda.get((dia, hora), []),
                    )
                    for dia in dias
                ],
            )
        )
        actual += BLOQUE
    return filas
