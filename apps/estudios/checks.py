"""
System check: el catálogo de la BD y las definiciones en código deben coincidir.

Consulta la BD, así que solo corre cuando Django pasa `databases`: en `migrate` (falla el
despliegue si no coinciden) y con `python manage.py check --database default`.
Si la app tiene migraciones pendientes no revisa nada: esas migraciones son las que
cargan las filas nuevas del catálogo.
"""

from django.core.checks import Error, Tags, register
from django.db import connections
from django.db.migrations.executor import MigrationExecutor

from apps.estudios.definiciones import REGISTRO


@register('estudios', Tags.database)
def revisar_catalogo(app_configs=None, databases=None, **kwargs):
    errores = []
    for alias in databases:
        if _migraciones_pendientes(alias):
            continue
        from apps.estudios.models import Estudio

        filas = dict(Estudio.objects.using(alias).values_list('clave', 'version_definicion'))
        en_codigo = {clave: definicion.version for clave, definicion in REGISTRO.items()}
        errores.extend(diferencias(en_codigo, filas))
    return errores


def diferencias(en_codigo: dict[str, int], en_bd: dict[str, int]) -> list[Error]:
    errores = []
    for clave in sorted(en_codigo.keys() - en_bd.keys()):
        errores.append(
            Error(
                f'La definición {clave!r} no tiene fila en la tabla de estudios.',
                hint='Agréguela al catálogo con una migración de datos.',
                id='estudios.E001',
            )
        )
    for clave in sorted(en_bd.keys() - en_codigo.keys()):
        errores.append(
            Error(
                f'El estudio {clave!r} de la BD no tiene definición en código.',
                hint='Cree su clase en apps/estudios/definiciones/ con @registrar.',
                id='estudios.E002',
            )
        )
    for clave in sorted(en_codigo.keys() & en_bd.keys()):
        if en_codigo[clave] != en_bd[clave]:
            errores.append(
                Error(
                    f'El estudio {clave!r} está en la versión {en_bd[clave]} en la BD '
                    f'y en la {en_codigo[clave]} en código.',
                    hint='Actualice `version_definicion` con una migración de datos.',
                    id='estudios.E003',
                )
            )
    return errores


def _migraciones_pendientes(alias: str) -> bool:
    executor = MigrationExecutor(connections[alias])
    plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
    return any(migracion.app_label == 'estudios' for migracion, _ in plan)
