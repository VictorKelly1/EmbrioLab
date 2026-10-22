import datetime

from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import DateTimeRangeField, RangeOperators
from django.db import models

DURACION = datetime.timedelta(minutes=30)


class TsTzRange(models.Func):
    function = 'TSTZRANGE'
    output_field = DateTimeRangeField()


class EstadoCita(models.TextChoices):
    PROGRAMADA = 'programada', 'Programada'
    ATENDIDA = 'atendida', 'Atendida'
    NO_ATENDIDA = 'no_atendida', 'No atendida'


class OrigenCita(models.TextChoices):
    AGENDADA = 'agendada', 'Agendada'
    ESPONTANEA = 'espontanea', 'Sin cita'


class Cita(models.Model):
    """
    Dura 30 minutos fijos y no puede empalmarse con otra (CONTEXTO.md §3).
    Cancelar = borrar. Reprogramar = cambiar fecha_hora.
    """

    recepcionista = models.ForeignKey(
        'cuentas.Recepcionista', on_delete=models.PROTECT, related_name='citas'
    )
    paciente = models.ForeignKey(
        'pacientes.Paciente', on_delete=models.PROTECT, related_name='citas'
    )
    fecha_hora = models.DateTimeField('fecha y hora')
    # Siempre fecha_hora + 30 min. Se guarda porque `timestamptz + interval` no es inmutable
    # en PostgreSQL y la restricción contra empalmes necesita una expresión inmutable.
    fecha_fin = models.DateTimeField(editable=False)
    asunto = models.CharField(max_length=200, blank=True)
    estado = models.CharField(
        max_length=12, choices=EstadoCita.choices, default=EstadoCita.PROGRAMADA
    )
    origen = models.CharField(
        max_length=10, choices=OrigenCita.choices, default=OrigenCita.AGENDADA
    )
    # Copia del folio del paciente: es el mismo en todas sus citas.
    numero_folio = models.CharField('folio', max_length=30)
    # Solo el hash SHA-256 del token; el token en claro nunca se guarda.
    token_qr = models.CharField(max_length=64, blank=True, editable=False)
    token_expiracion = models.DateTimeField(null=True, blank=True, editable=False)
    recordatorio_enviado = models.BooleanField(default=False)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['fecha_hora']
        indexes = [models.Index(fields=['fecha_hora'], name='cita_fecha_hora_idx')]
        constraints = [
            ExclusionConstraint(
                name='cita_sin_empalmes',
                expressions=[
                    (TsTzRange('fecha_hora', 'fecha_fin'), RangeOperators.OVERLAPS),
                ],
                violation_error_message='Ya hay una cita en ese horario.',
            ),
            models.CheckConstraint(
                condition=models.Q(fecha_fin=models.F('fecha_hora') + DURACION),
                name='cita_dura_30_minutos',
            ),
            models.CheckConstraint(
                condition=models.Q(estado__in=EstadoCita.values), name='cita_estado_valido'
            ),
            models.CheckConstraint(
                condition=models.Q(origen__in=OrigenCita.values), name='cita_origen_valido'
            ),
            models.UniqueConstraint(
                fields=['token_qr'],
                condition=~models.Q(token_qr=''),
                name='cita_token_qr_unico',
            ),
        ]

    def __str__(self):
        return f'{self.numero_folio} · {self.fecha_hora:%Y-%m-%d %H:%M}'

    def save(self, *args, **kwargs):
        self.fecha_fin = self.fecha_hora + DURACION
        update_fields = kwargs.get('update_fields')
        if update_fields is not None and 'fecha_hora' in update_fields:
            kwargs['update_fields'] = {*update_fields, 'fecha_fin'}
        super().save(*args, **kwargs)
