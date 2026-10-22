from django.conf import settings
from django.db import models

from apps.core.models import ModeloConTiempos
from apps.formularios.esquema import validar_esquema
from apps.personas.models import Genero


class Formulario(ModeloConTiempos):
    """Cuestionario de la visita. En la Fase 1 hay dos fijos (hombre y mujer)."""

    nombre = models.CharField(max_length=150)
    descripcion = models.TextField(blank=True)
    # Vacío = aplica a todos los géneros.
    genero_aplicable = models.CharField(
        max_length=10, choices=Genero.choices, blank=True, default=''
    )
    activo = models.BooleanField(default=True)
    usuario_creador = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+'
    )

    class Meta:
        ordering = ['nombre']

    def __str__(self):
        return self.nombre

    @property
    def fecha_creacion(self):
        return self.creado_en

    @property
    def para_quien(self) -> str:
        return {'masculino': 'Para hombres', 'femenino': 'Para mujeres'}.get(
            self.genero_aplicable, 'Para todos'
        )


class VersionFormulario(models.Model):
    """
    El esquema nunca se edita: cada cambio es una versión nueva. Así cada respuesta
    guardada conserva las preguntas exactas que vio el paciente.
    """

    formulario = models.ForeignKey(Formulario, on_delete=models.PROTECT, related_name='versiones')
    numero_version = models.PositiveIntegerField()
    esquema = models.JSONField()
    publicada = models.BooleanField(default=False)
    fecha_publicacion = models.DateTimeField(null=True, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['formulario', '-numero_version']
        verbose_name = 'versión de formulario'
        verbose_name_plural = 'versiones de formulario'
        constraints = [
            models.UniqueConstraint(
                fields=['formulario', 'numero_version'], name='version_formulario_numero_unico'
            ),
            # Solo una versión publicada por formulario (índice único parcial).
            models.UniqueConstraint(
                fields=['formulario'],
                condition=models.Q(publicada=True),
                name='version_formulario_una_publicada',
            ),
        ]

    def __str__(self):
        return f'{self.formulario} v{self.numero_version}'

    def clean(self):
        validar_esquema(self.esquema)


class FormularioLlenado(models.Model):
    """Respuestas de la visita. Una por cita: el link es de un solo uso."""

    cita = models.OneToOneField(
        'citas.Cita', on_delete=models.PROTECT, related_name='formulario_llenado'
    )
    version_formulario = models.ForeignKey(
        VersionFormulario, on_delete=models.PROTECT, related_name='llenados'
    )
    respuestas = models.JSONField()
    fecha_llenado = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'formulario llenado'
        verbose_name_plural = 'formularios llenados'

    def __str__(self):
        return f'{self.version_formulario} · cita {self.cita_id}'
