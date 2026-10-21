import datetime
import uuid
from pathlib import Path

from django.contrib.postgres.indexes import GinIndex, OpClass
from django.core.exceptions import ValidationError
from django.core.files.storage import storages
from django.core.validators import EmailValidator, RegexValidator
from django.db import models
from django.utils import timezone

from apps.core.models import ModeloConTiempos
from apps.core.texto import normalizar

# Solo dígitos, con lada; opcionalmente con + y código de país.
TELEFONO_REGEX = r'^\+?[0-9]{10,15}$'

# 4 letras, fecha AAMMDD, sexo, entidad (2) + consonantes (3), homoclave y dígito verificador.
CURP_REGEX = r'^[A-Z]{4}[0-9]{6}[HMX][A-Z]{5}[A-Z0-9][0-9]$'


class Genero(models.TextChoices):
    MASCULINO = 'masculino', 'Masculino'
    FEMENINO = 'femenino', 'Femenino'


def _almacenamiento_privado():
    return storages['privado']


def _ruta_foto(persona, nombre_archivo):
    # Nombre aleatorio: el nombre original puede traer datos del paciente.
    return f'fotos/{uuid.uuid4().hex}{Path(nombre_archivo).suffix.lower()}'


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
    foto = models.ImageField(upload_to=_ruta_foto, storage=_almacenamiento_privado, blank=True)
    # Nombre completo normalizado (sin acentos ni mayúsculas) para la búsqueda por trigramas.
    # Se calcula en save(); no se edita a mano.
    nombre_busqueda = models.CharField(max_length=310, editable=False, default='')

    class Meta:
        indexes = [
            GinIndex(
                OpClass('nombre_busqueda', name='gin_trgm_ops'),
                name='persona_nombre_trgm',
            ),
        ]
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

    def save(self, *args, **kwargs):
        self.nombre_busqueda = normalizar(self.nombre_completo)
        update_fields = kwargs.get('update_fields')
        if update_fields is not None:
            kwargs['update_fields'] = {*update_fields, 'nombre_busqueda'}
        super().save(*args, **kwargs)

    def edad_en(self, fecha: datetime.date) -> int:
        """Años cumplidos en `fecha`."""
        nacimiento = self.fecha_nacimiento
        aun_no_cumple = (fecha.month, fecha.day) < (nacimiento.month, nacimiento.day)
        return fecha.year - nacimiento.year - aun_no_cumple

    @property
    def edad(self) -> int:
        return self.edad_en(timezone.localdate())

    @property
    def nombre_completo(self):
        partes = [self.nombre, self.apellido_paterno, self.apellido_materno]
        return ' '.join(p for p in partes if p)


class TipoContacto(models.TextChoices):
    TELEFONO = 'telefono', 'Teléfono'
    WHATSAPP = 'whatsapp', 'WhatsApp'
    CORREO = 'correo', 'Correo electrónico'


class Contacto(ModeloConTiempos):
    persona = models.ForeignKey(Persona, on_delete=models.CASCADE, related_name='contactos')
    tipo = models.CharField(max_length=10, choices=TipoContacto.choices)
    valor = models.CharField(max_length=254)
    principal = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(tipo__in=TipoContacto.values), name='contacto_tipo_valido'
            ),
            # A lo más un contacto principal de cada tipo por persona.
            models.UniqueConstraint(
                fields=['persona', 'tipo'],
                condition=models.Q(principal=True),
                name='contacto_un_principal_por_tipo',
            ),
            models.UniqueConstraint(
                fields=['persona', 'tipo', 'valor'], name='contacto_sin_duplicados'
            ),
        ]

    def __str__(self):
        return f'{self.get_tipo_display()}: {self.valor}'

    def clean(self):
        if self.tipo == TipoContacto.CORREO:
            validador = EmailValidator('Correo electrónico inválido.')
        else:
            validador = RegexValidator(
                TELEFONO_REGEX, 'Escriba el número con lada: 10 dígitos (o +código de país).'
            )
        try:
            validador(self.valor)
        except ValidationError as error:
            raise ValidationError({'valor': error.messages}) from error
