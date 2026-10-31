FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Bibliotecas de sistema que usa WeasyPrint para generar los PDF de resultados.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Mismo UID que el usuario de desarrollo para que el código montado no cambie de dueño.
RUN useradd --uid 1000 --create-home app \
    && mkdir -p /app/staticfiles /app/privado \
    && chown app:app /app/staticfiles /app/privado

COPY --chown=app:app . .

USER app

EXPOSE 8000
