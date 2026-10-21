from django.db import transaction

from apps.core.models import ModeloBorradoLogico


@transaction.atomic
def dar_de_baja(instancia: ModeloBorradoLogico) -> None:
    instancia.estado_actividad = False
    instancia.save(update_fields=['estado_actividad', 'actualizado_en'])


@transaction.atomic
def reactivar(instancia: ModeloBorradoLogico) -> None:
    instancia.estado_actividad = True
    instancia.save(update_fields=['estado_actividad', 'actualizado_en'])
