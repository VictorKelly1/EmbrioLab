import datetime

from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import DateTimeRangeField, RangeOperators
from django.db import models

from apps.personas.models import Genero

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

    Se puede agendar SIN paciente registrado: la cita guarda solo nombre, apellido
    paterno, género (para elegir el formulario) y teléfono o correo (para el recordatorio).
    Al llegar, la recepción liga o registra al paciente; atendida siempre tiene paciente.
    """

    recepcionista = models.ForeignKey(
        'cuentas.Recepcionista', on_delete=models.PROTECT, related_name='citas'
    )
    paciente = models.ForeignKey(
        'pacientes.Paciente',
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='citas',
    )
    # Quien agendó sin estar registrado. Se conservan al registrar su llegada.
    nombre = models.CharField(max_length=100, blank=True)
    apellido_paterno = models.CharField(max_length=100, blank=True)
    genero = models.CharField('género', max_length=10, choices=Genero.choices, blank=True)
    # PROVISIONAL (CONTEXTO.md §8): se usa como WhatsApp para el recordatorio y el link.
    telefono = models.CharField('teléfono', max_length=16, blank=True)
    correo = models.EmailField(blank=True)
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
    # Copia del folio del paciente: es el mismo en todas sus citas. Vacío sin paciente.
    numero_folio = models.CharField('folio', max_length=30, blank=True)
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
            # Atendida = el paciente llegó y ya está registrado.
            models.CheckConstraint(
                condition=~models.Q(estado=EstadoCita.ATENDIDA) | models.Q(paciente__isnull=False),
                name='cita_atendida_con_paciente',
            ),
            # Sin paciente, la cita lleva los datos mínimos de quien la agendó.
            models.CheckConstraint(
                condition=models.Q(paciente__isnull=False)
                | (
                    ~models.Q(nombre='')
                    & ~models.Q(apellido_paterno='')
                    & models.Q(genero__in=Genero.values)
                    & (~models.Q(telefono='') | ~models.Q(correo=''))
                ),
                name='cita_sin_paciente_con_datos',
            ),
        ]

    def __str__(self):
        return f'{self.numero_folio or self.nombre_paciente} · {self.fecha_hora:%Y-%m-%d %H:%M}'

    def save(self, *args, **kwargs):
        self.fecha_fin = self.fecha_hora + DURACION
        update_fields = kwargs.get('update_fields')
        if update_fields is not None and 'fecha_hora' in update_fields:
            kwargs['update_fields'] = {*update_fields, 'fecha_fin'}
        super().save(*args, **kwargs)

    @property
    def sin_registro(self) -> bool:
        return self.paciente_id is None

    @property
    def nombre_paciente(self) -> str:
        """El nombre completo del paciente, o el que dio al agendar sin registro."""
        if self.paciente_id:
            return self.paciente.persona.nombre_completo
        return f'{self.nombre} {self.apellido_paterno}'.strip()

    @property
    def nombre_de_pila(self) -> str:
        """Para el saludo de los mensajes."""
        return self.paciente.persona.nombre if self.paciente_id else self.nombre

    @property
    def genero_paciente(self) -> str:
        """Elige el formulario de la visita (CONTEXTO.md §3)."""
        return self.paciente.persona.genero if self.paciente_id else self.genero
