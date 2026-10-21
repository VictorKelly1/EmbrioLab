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
