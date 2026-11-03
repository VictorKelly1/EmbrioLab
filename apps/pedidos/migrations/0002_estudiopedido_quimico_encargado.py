import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('cuentas', '0001_initial'),
        ('pedidos', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='estudiopedido',
            name='quimico_encargado',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='estudios_encargados',
                to='cuentas.quimico',
            ),
        ),
        migrations.AddField(
            model_name='estudiopedido',
            name='fecha_toma',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
