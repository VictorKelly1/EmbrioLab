import datetime

import factory
from django.utils import timezone

from apps.citas.models import Cita
from apps.cuentas.tests.factories import RecepcionistaFactory
from apps.pacientes.tests.factories import PacienteFactory


def en(dias: int, hora: int = 10, minuto: int = 0) -> datetime.datetime:
    """Fecha y hora local dentro de `dias` días (negativo = en el pasado)."""
    fecha = timezone.localdate() + datetime.timedelta(days=dias)
    return timezone.make_aware(datetime.datetime.combine(fecha, datetime.time(hora, minuto)))


class CitaFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Cita

    recepcionista = factory.SubFactory(RecepcionistaFactory)
    paciente = factory.SubFactory(PacienteFactory)
    fecha_hora = factory.Sequence(lambda n: en(1 + n, 10))
    numero_folio = factory.LazyAttribute(lambda cita: cita.paciente.folio)
