"""Modelos base abstractos que heredan los modelos del dominio."""

from django.db import models


class BorradoFisicoNoPermitido(Exception):
    """Se lanza al intentar borrar físicamente un registro con borrado lógico."""


class ModeloConTiempos(models.Model):
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class BorradoLogicoQuerySet(models.QuerySet):
    def activos(self):
        return self.filter(estado_actividad=True)

    def inactivos(self):
        return self.filter(estado_actividad=False)

    def delete(self):
        raise BorradoFisicoNoPermitido('Usa core.services.dar_de_baja().')


class ModeloBorradoLogico(ModeloConTiempos):
    """Registros que nunca se eliminan: se marcan inactivos (CONTEXTO.md §3)."""

    estado_actividad = models.BooleanField(default=True)

    objects = BorradoLogicoQuerySet.as_manager()

    class Meta:
        abstract = True

    def delete(self, *args, **kwargs):
        raise BorradoFisicoNoPermitido('Usa core.services.dar_de_baja().')


class ContadorIntentos(models.Model):
    """
    Contador por ventana de tiempo para limitar peticiones (core/limites.py).
    Una fila por clave, por ejemplo 'formulario:ip:203.0.113.5'.
    """

    clave = models.CharField(max_length=200, unique=True)
    inicio_ventana = models.DateTimeField()
    conteo = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name_plural = 'contadores de intentos'

    def __str__(self):
        return f'{self.clave}: {self.conteo}'
