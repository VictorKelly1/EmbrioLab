from django.core.validators import RegexValidator
from django.db import models

from apps.core.models import ModeloConTiempos

# 4 letras, fecha AAMMDD, sexo, entidad (2) + consonantes (3), homoclave y dígito verificador.
CURP_REGEX = r'^[A-Z]{4}[0-9]{6}[HMX][A-Z]{5}[A-Z0-9][0-9]$'


class Genero(models.TextChoices):
    MASCULINO = 'masculino', 'Masculino'
    FEMENINO = 'femenino', 'Femenino'


class Direccion(ModeloConTiempos):
    """Sin propietario: varias personas pueden compartir una dirección."""

    calle = models.CharField(max_length=150)
    numero = models.CharField(max_length=20)
    colonia_frac = models.CharField('colonia o fraccionamiento', max_length=150)
    ciudad = models.CharField(max_length=100)
    estado = models.CharField(max_length=100)
    pais = models.CharField(max_length=100, default='México')
    codigo_postal = models.CharField(max_length=10)

    class Meta:
        verbose_name = 'dirección'
        verbose_name_plural = 'direcciones'

    def __str__(self):
        return f'{self.calle} {self.numero}, {self.colonia_frac}, {self.ciudad}'


class Persona(ModeloConTiempos):
    direccion = models.ForeignKey(
        Direccion, null=True, blank=True, on_delete=models.SET_NULL, related_name='personas'
    )
    nombre = models.CharField(max_length=100)
    apellido_paterno = models.CharField(max_length=100)
    # Vacío para quien no tiene; la regla del folio en ese caso la decide el cliente.
    apellido_materno = models.CharField(max_length=100, blank=True)
    genero = models.CharField(max_length=10, choices=Genero.choices)
    fecha_nacimiento = models.DateField()
    numero_ine = models.CharField('número de INE', max_length=20, blank=True)
    curp = models.CharField(
        'CURP',
        max_length=18,
        unique=True,
        validators=[RegexValidator(CURP_REGEX, 'CURP con formato inválido.')],
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(curp__regex=CURP_REGEX), name='persona_curp_formato'
            ),
            models.CheckConstraint(
                condition=models.Q(genero__in=Genero.values), name='persona_genero_valido'
            ),
        ]

    def __str__(self):
        return self.nombre_completo

    @property
    def nombre_completo(self):
        partes = [self.nombre, self.apellido_paterno, self.apellido_materno]
        return ' '.join(p for p in partes if p)
