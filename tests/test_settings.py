import os
import subprocess
import sys

from django.conf import settings


def test_localizacion():
    assert settings.LANGUAGE_CODE == 'es-mx'
    assert settings.USE_TZ is True
    assert settings.TIME_ZONE == os.environ.get('DJANGO_TIME_ZONE', 'America/Mexico_City')


def test_base_de_datos_es_postgresql():
    assert settings.DATABASES['default']['ENGINE'] == 'django.db.backends.postgresql'


def _check_prod(**env):
    return subprocess.run(
        [sys.executable, 'manage.py', 'check'],
        env={**os.environ, 'DJANGO_SETTINGS_MODULE': 'embriolab.settings.prod', **env},
        capture_output=True,
        text=True,
    )


def test_prod_carga_con_hosts():
    resultado = _check_prod(DJANGO_ALLOWED_HOSTS='lab.example.com')
    assert resultado.returncode == 0, resultado.stderr


def test_prod_exige_allowed_hosts():
    resultado = _check_prod(DJANGO_ALLOWED_HOSTS='')
    assert resultado.returncode != 0
    assert 'DJANGO_ALLOWED_HOSTS' in resultado.stderr
