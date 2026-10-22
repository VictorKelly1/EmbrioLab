import datetime

from django.db.models import QuerySet
from django.utils import timezone

from apps.citas.models import Cita, EstadoCita
from apps.pacientes.models import Paciente


def _citas() -> QuerySet[Cita]:
    return Cita.objects.select_related('paciente__persona')


def citas_entre(inicio: datetime.datetime, fin: datetime.datetime) -> QuerySet[Cita]:
    """Citas que empiezan en [inicio, fin), en orden."""
    return _citas().filter(fecha_hora__gte=inicio, fecha_hora__lt=fin)


def citas_del_dia(fecha: datetime.date) -> QuerySet[Cita]:
    inicio = timezone.make_aware(datetime.datetime.combine(fecha, datetime.time.min))
    return citas_entre(inicio, inicio + datetime.timedelta(days=1))


def proximas_citas(limite: int = 8) -> QuerySet[Cita]:
    return _citas().filter(estado=EstadoCita.PROGRAMADA, fecha_fin__gt=timezone.now())[:limite]


def citas_de_paciente(paciente: Paciente) -> QuerySet[Cita]:
    return (
        Cita.objects.filter(paciente=paciente)
        .select_related('formulario_llenado')
        .order_by('-fecha_hora')
    )


def obtener_cita(pk: int) -> Cita:
    return (
        _citas()
        .select_related('recepcionista__usuario__persona', 'formulario_llenado__version_formulario')
        .get(pk=pk)
    )


def _al_bloque(momento: datetime.datetime) -> datetime.datetime:
    """Redondea hacia arriba al siguiente :00 o :30 en hora local."""
    momento = timezone.localtime(momento).replace(second=0, microsecond=0)
    if momento.minute % 30:
        momento += datetime.timedelta(minutes=30 - momento.minute % 30)
    return momento


def siguiente_horario_libre(desde: datetime.datetime) -> datetime.datetime:
    """Primer bloque de :00 o :30, desde `desde`, que no se empalma con otra cita."""
    inicio = _al_bloque(desde)
    citas = list(
        Cita.objects.filter(fecha_fin__gt=inicio)
        .order_by('fecha_hora')
        .values_list('fecha_hora', 'fecha_fin')[:200]
    )
    for empieza, termina in citas:
        if inicio + datetime.timedelta(minutes=30) <= empieza:
            break
        if termina > inicio:
            inicio = _al_bloque(termina)
    return inicio
