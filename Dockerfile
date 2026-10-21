FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Mismo UID que el usuario de desarrollo para que el código montado no cambie de dueño.
RUN useradd --uid 1000 --create-home app \
    && mkdir -p /app/staticfiles \
    && chown app:app /app/staticfiles

COPY --chown=app:app . .

USER app

EXPOSE 8000
