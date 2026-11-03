"""
Un solo encargado por estudio (cola de químicos): se queda el primer químico asignado,
con la fecha de su asignación como fecha de toma.
"""

from django.db import migrations


def copiar(apps, schema_editor):
    EstudioPedido = apps.get_model('pedidos', 'EstudioPedido')
    AsignacionQuimico = apps.get_model('pedidos', 'AsignacionQuimico')
    vistos = set()
    for asignacion in AsignacionQuimico.objects.order_by('fecha_asignacion', 'id'):
        if asignacion.estudio_pedido_id in vistos:
            continue
        vistos.add(asignacion.estudio_pedido_id)
        EstudioPedido.objects.filter(pk=asignacion.estudio_pedido_id).update(
            quimico_encargado_id=asignacion.quimico_id,
            fecha_toma=asignacion.fecha_asignacion,
        )


def regresar(apps, schema_editor):
    EstudioPedido = apps.get_model('pedidos', 'EstudioPedido')
    AsignacionQuimico = apps.get_model('pedidos', 'AsignacionQuimico')
    for estudio in EstudioPedido.objects.filter(quimico_encargado__isnull=False):
        asignacion = AsignacionQuimico.objects.create(
            estudio_pedido=estudio, quimico_id=estudio.quimico_encargado_id
        )
        # auto_now_add no deja fijar la fecha al crear.
        AsignacionQuimico.objects.filter(pk=asignacion.pk).update(
            fecha_asignacion=estudio.fecha_toma
        )


class Migration(migrations.Migration):
    dependencies = [
        ('pedidos', '0002_estudiopedido_quimico_encargado'),
    ]

    operations = [
        migrations.RunPython(copiar, regresar),
    ]
