from django.db import models

from apps.core.models import ModeloBorradoLogico, ModeloConTiempos
from apps.pacientes.folio import generar_folio

# El número se toma de esta secuencia de PostgreSQL (migración 0001): es seguro con
# registros simultáneos y no se repite aunque se reviertan transacciones.
SECUENCIA_NUMERO = 'pacientes_paciente_numero_seq'


class Paciente(ModeloBorradoLogico):
    """Se registra una sola vez y nunca se elimina: se da de baja (CONTEXTO.md §3)."""

    persona = models.OneToOneField(
        'personas.Persona', on_delete=models.PROTECT, related_name='paciente'
    )
    numero = models.PositiveIntegerField('número de paciente', unique=True, editable=False)
    fecha_registro = models.DateField(auto_now_add=True)

    class Meta:
        ordering = ['-numero']

    def __str__(self):
        return f'{self.numero} · {self.persona}'

    @property
    def folio(self) -> str:
        return generar_folio(
            self.persona.apellido_paterno, self.persona.apellido_materno, self.numero
        )


class Doctor(ModeloConTiempos):
    """El doctor que firma la orden. Se relaciona con los pedidos (semana 6)."""

    nombre = models.CharField(max_length=200)
    contacto = models.CharField(max_length=200, blank=True)

    class Meta:
        verbose_name_plural = 'doctores'
        ordering = ['nombre']

    def __str__(self):
        return self.nombre
