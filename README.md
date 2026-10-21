# EmbrioLab

Sistema web de gestión para el laboratorio clínico EmbrioLab (Django + HTMX + PostgreSQL).
Antes de trabajar en el repo, lee `CONTEXTO.md`.

## Desarrollo local

```bash
cp .env.example .env              # y ajusta los valores
docker compose up --build -d      # postgres + Django en http://localhost:8000
docker compose exec web python manage.py migrate
docker compose exec web python manage.py crear_admin
```

- Pruebas: `docker compose exec web pytest`
- Lint y formato: `docker compose exec web ruff check .` y `docker compose exec web ruff format .`
- Logs: `docker compose logs -f web`
- Las fotos de las personas se guardan en `privado/` (fuera del repo y sin URL pública;
  configurable con `DJANGO_PRIVATE_MEDIA_ROOT`). En producción es el volumen `privado`.

## Producción

`docker compose -f docker-compose.prod.yml up --build -d` levanta postgres + gunicorn + nginx
con `embriolab.settings.prod`. El HTTPS se configura cuando el cliente defina hosting y dominio.
