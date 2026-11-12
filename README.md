# EmbrioLab

Sistema web de gestión para el laboratorio clínico EmbrioLab (Django + HTMX + PostgreSQL).
Antes de trabajar en el repo, lee `CONTEXTO.md`.

## Desarrollo local

```bash
cp .env.example .env              # en desarrollo sirve tal cual
docker compose up --build -d      # postgres + Django en http://localhost:8000 + worker + recordatorios
docker compose exec web python manage.py migrate
docker compose restart worker recordatorios   # arrancan antes de que existan las tablas
docker compose exec web python manage.py cargar_demo --confirmar --con-usuarios
```

El último paso crea los usuarios de ejemplo y un escenario con pacientes, citas y pedidos en
todos los estados. Entre en http://localhost:8000 con cualquiera de ellos; la contraseña sale
en la terminal (o fíjela antes con `DEMO_PASSWORD=...` en `.env`):

| Correo | Rol |
|---|---|
| `admin@embriolab.local` | Administrador |
| `recepcion@embriolab.local` | Recepcionista |
| `quimico@embriolab.local` | Químico (Rubén) |
| `quimico2@embriolab.local` | Químico (Laura) |

Para un administrador con datos propios: `docker compose exec web python manage.py crear_admin`.

- Reiniciar los datos de ejemplo (solo con `DEBUG=True`): `docker compose exec web python manage.py cargar_demo --confirmar`.
  BORRA pacientes, doctores, citas, pedidos y notificaciones y carga un escenario con todos los
  estados del flujo. Conserva los usuarios, el catálogo y los formularios de las migraciones.
  Necesita al menos una recepcionista y un químico activos. Con `--solo-borrar` no carga nada.
- Si cambia el código de las tareas o el comando de recordatorios, reinicie esos servicios:
  `docker compose restart worker recordatorios` (no se recargan solos).
- Pruebas: `docker compose exec web pytest`
- Lint y formato: `docker compose exec web ruff check .` y `docker compose exec web ruff format .`
- CI (`.github/workflows/ci.yml`): en cada PR corre ruff, `makemigrations --check`, `check --deploy`
  con los settings de producción y pytest. `main` no acepta el merge si falla.
- Permisos: `apps/core/tests/test_permisos.py` es la matriz de quién entra a cada URL. Una URL
  nueva hace fallar las pruebas hasta que se agrega ahí.
- Logs: `docker compose logs -f web`
- Notificaciones: el servicio `worker` (`manage.py db_worker`) las envía; en desarrollo los
  correos se imprimen en su consola: `docker compose logs -f worker`. El servicio
  `recordatorios` encola cada 15 minutos los recordatorios de las citas de las próximas 24 h.
- Las fotos de las personas se guardan en `privado/` (fuera del repo y sin URL pública;
  configurable con `DJANGO_PRIVATE_MEDIA_ROOT`). En producción es el volumen `privado`.

## Formularios del cliente

Cada versión de un formulario es un archivo JSON en `apps/formularios/datos/` (`hombre_v1.json`,
`mujer_v1.json`, …). El formato está en `apps/formularios/carga.py` y el de las preguntas en
`apps/formularios/esquema.py`. Los `_v1` son las preguntas provisionales actuales.

1. Escriba el archivo nuevo, con el siguiente número: `hombre_v2.json`. **No edite uno que ya
   use una migración**: cada cambio es un archivo y una migración nuevos.
2. Revíselo. El comando no cambia nada en la BD:
   ```
   docker compose exec web python manage.py revisar_formulario apps/formularios/datos/hombre_v2.json --html privado/vista.html
   ```
   Dice si es válido, lista las preguntas, compara con lo publicado (agregadas, quitadas,
   cambiadas) y genera `vista.html`: así lo verá el paciente. Es un solo archivo que puede
   mandarle al cliente para que lo apruebe.
3. Publíquelo con una migración de datos (`makemigrations formularios --empty -n formularios_v2`):
   ```python
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
   ```
   Actualiza el formulario activo de su género (aunque cambie el nombre) y despublica la versión
   anterior. Las respuestas ya guardadas conservan la versión con la que se llenaron. La prueba
   `test_lo_publicado_coincide_con_el_ultimo_archivo_de_cada_genero` falla si un archivo nuevo
   no tiene su migración.

## Producción

`docker compose -f docker-compose.prod.yml up --build -d` levanta postgres + gunicorn + nginx
+ worker + recordatorios con `embriolab.settings.prod`. Requiere en `.env` `SITIO_URL` y la cuenta SMTP. El HTTPS se configura cuando el cliente defina hosting y dominio.
