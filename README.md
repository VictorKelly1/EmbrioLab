# EmbrioLab

Sistema web de gestión para el laboratorio clínico EmbrioLab (Django + HTMX + PostgreSQL).
Antes de trabajar en el repo, lee `CONTEXTO.md`.

## Desarrollo local

```bash
cp .env.example .env              # y ajusta los valores
docker compose up --build -d      # postgres + Django en http://localhost:8000 + worker + recordatorios
docker compose exec web python manage.py migrate
docker compose exec web python manage.py crear_admin
```

- Datos de ejemplo (solo con `DEBUG=True`): `docker compose exec web python manage.py cargar_demo --confirmar`.
  BORRA pacientes, doctores, citas, pedidos y notificaciones y carga un escenario con todos los
  estados del flujo. Conserva los usuarios, el catálogo y los formularios de las migraciones.
  Necesita al menos una recepcionista y un químico activos. Con `--solo-borrar` no carga nada.
- Si cambia el código de las tareas o el comando de recordatorios, reinicie esos servicios:
  `docker compose restart worker recordatorios` (no se recargan solos).
- Pruebas: `docker compose exec web pytest`
- Lint y formato: `docker compose exec web ruff check .` y `docker compose exec web ruff format .`
- Logs: `docker compose logs -f web`
- Notificaciones: el servicio `worker` (`manage.py db_worker`) las envía; en desarrollo los
  correos se imprimen en su consola: `docker compose logs -f worker`. El servicio
  `recordatorios` encola cada 15 minutos los recordatorios de las citas de las próximas 24 h.
- Las fotos de las personas se guardan en `privado/` (fuera del repo y sin URL pública;
  configurable con `DJANGO_PRIVATE_MEDIA_ROOT`). En producción es el volumen `privado`.

## Producción

`docker compose -f docker-compose.prod.yml up --build -d` levanta postgres + gunicorn + nginx
+ worker + recordatorios con `embriolab.settings.prod`. Requiere en `.env` `SITIO_URL` y la cuenta SMTP. El HTTPS se configura cuando el cliente defina hosting y dominio.
