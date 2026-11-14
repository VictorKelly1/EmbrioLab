"""Publica los formularios del cliente (hombre y mujer). El de donantes queda sin publicar."""

from django.db import migrations

from apps.formularios.carga import DATOS, leer, publicar


def cargar(apps, schema_editor):
    modelos = {
        'Formulario': apps.get_model('formularios', 'Formulario'),
        'VersionFormulario': apps.get_model('formularios', 'VersionFormulario'),
    }
    for archivo in ('hombre_v2.json', 'mujer_v2.json'):
        publicar(leer(DATOS / archivo), **modelos)


class Migration(migrations.Migration):
    dependencies = [('formularios', '0002_formularios_provisionales')]
    operations = [migrations.RunPython(cargar, migrations.RunPython.noop)]
