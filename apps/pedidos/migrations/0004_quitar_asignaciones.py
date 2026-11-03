from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('pedidos', '0003_copiar_asignaciones'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='estudiopedido',
            name='quimicos_asignados',
        ),
        migrations.DeleteModel(
            name='AsignacionQuimico',
        ),
        migrations.AddConstraint(
            model_name='estudiopedido',
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(
                        ('estado', 'pendiente'),
                        ('fecha_toma__isnull', True),
                        ('quimico_encargado__isnull', True),
                    ),
                    models.Q(
                        ('estado', 'en_proceso'),
                        ('fecha_toma__isnull', False),
                        ('quimico_encargado__isnull', False),
                    ),
                    ('estado', 'completado'),
                    _connector='OR',
                ),
                name='estudio_pedido_encargado_segun_estado',
            ),
        ),
    ]
