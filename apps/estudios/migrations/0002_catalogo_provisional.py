"""
Catálogo de la Fase 1: categorías y estudios (CONTEXTO.md §6, semana 5).

PROVISIONAL: 3 estudios de ejemplo, con precios, alias y valores de referencia
inventados, mientras el cliente entrega su Excel. Cada estudio necesita su definición
en apps/estudios/definiciones/ con la misma clave (lo revisa el system check).
Los reales se cargan con otra migración de datos (no se edita esta).
"""

import datetime
from decimal import Decimal

from django.db import migrations

CATEGORIAS = ('Sanguíneos', 'Esperma', 'Cultivo', 'Otros')

# clave, nombre, categoría, precio
ESTUDIOS = (
    ('GLU', 'Glucosa en ayuno', 'Sanguíneos', Decimal('120.00')),
    ('PLIP', 'Perfil de lípidos', 'Sanguíneos', Decimal('450.00')),
    ('ESP', 'Espermatobioscopia básica', 'Esperma', Decimal('800.00')),
)

ALIAS = {
    'GLU': ('glucosa', 'glucosa en ayunas', 'glicemia'),
    'PLIP': ('perfil lipidico', 'lipidos', 'colesterol y trigliceridos'),
    'ESP': ('espermatobioscopia', 'espermograma', 'seminograma'),
}

# clave, campo, género, valor mínimo, valor máximo, unidad
REFERENCIAS = (
    ('GLU', 'glucosa', '', Decimal(70), Decimal(99), 'mg/dL'),
    ('PLIP', 'colesterol_total', '', None, Decimal(200), 'mg/dL'),
    ('PLIP', 'hdl', 'masculino', Decimal(40), None, 'mg/dL'),
    ('PLIP', 'hdl', 'femenino', Decimal(50), None, 'mg/dL'),
    ('PLIP', 'trigliceridos', '', None, Decimal(150), 'mg/dL'),
    ('PLIP', 'ldl', '', None, Decimal(100), 'mg/dL'),
    ('ESP', 'volumen', '', Decimal('1.4'), None, 'mL'),
    ('ESP', 'concentracion', '', Decimal(16), None, 'millones/mL'),
    ('ESP', 'movilidad_progresiva', '', Decimal(30), None, '%'),
    ('ESP', 'total_espermatozoides', '', Decimal(39), None, 'millones'),
)

VIGENTE_DESDE = datetime.date(2026, 1, 1)


def crear(apps, schema_editor):
    Categoria = apps.get_model('estudios', 'CategoriaEstudio')
    Estudio = apps.get_model('estudios', 'Estudio')
    Alias = apps.get_model('estudios', 'EstudioAlias')
    Referencia = apps.get_model('estudios', 'ValorReferencia')

    categorias = {nombre: Categoria.objects.create(nombre=nombre) for nombre in CATEGORIAS}
    estudios = {
        clave: Estudio.objects.create(
            clave=clave, nombre=nombre, categoria=categorias[categoria], precio=precio
        )
        for clave, nombre, categoria, precio in ESTUDIOS
    }
    for clave, nombres in ALIAS.items():
        for alias in nombres:
            Alias.objects.create(estudio=estudios[clave], alias=alias)
    for clave, campo, genero, minimo, maximo, unidad in REFERENCIAS:
        Referencia.objects.create(
            estudio=estudios[clave],
            clave_campo=campo,
            genero=genero,
            valor_minimo=minimo,
            valor_maximo=maximo,
            unidad=unidad,
            vigente_desde=VIGENTE_DESDE,
        )


def borrar(apps, schema_editor):
    claves = [clave for clave, *_ in ESTUDIOS]
    apps.get_model('estudios', 'ValorReferencia').objects.filter(estudio__clave__in=claves).delete()
    apps.get_model('estudios', 'EstudioAlias').objects.filter(estudio__clave__in=claves).delete()
    apps.get_model('estudios', 'Estudio').objects.filter(clave__in=claves).delete()
    apps.get_model('estudios', 'CategoriaEstudio').objects.filter(nombre__in=CATEGORIAS).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('estudios', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(crear, borrar),
    ]
