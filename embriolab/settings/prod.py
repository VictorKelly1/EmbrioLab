"""
Settings de producción. Corre detrás de nginx, que termina el HTTPS.

Todo lo que depende del hosting (dominio, SMTP) sale de .env; el hosting lo decide el cliente.
"""

import os

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403
from .base import ALLOWED_HOSTS

DEBUG = False

if not ALLOWED_HOSTS:
    raise ImproperlyConfigured('DJANGO_ALLOWED_HOSTS es obligatorio en producción.')

CSRF_TRUSTED_ORIGINS = [
    o for o in os.environ.get('DJANGO_CSRF_TRUSTED_ORIGINS', '').split(',') if o
]

# nginx avisa con este header que la petición original llegó por HTTPS.
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_SSL_REDIRECT = os.environ.get('DJANGO_SECURE_SSL_REDIRECT', 'True') == 'True'

# El límite de intentos propio (core/limites.py) toma la IP de X-Forwarded-For.
IP_DESDE_PROXY = True

# axes debe tomar la IP real del cliente que nginx pone en X-Forwarded-For.
AXES_IPWARE_PROXY_COUNT = 1
AXES_IPWARE_META_PRECEDENCE_ORDER = ['HTTP_X_FORWARDED_FOR', 'REMOTE_ADDR']

SECURE_HSTS_SECONDS = int(os.environ.get('DJANGO_SECURE_HSTS_SECONDS', '31536000'))
SECURE_HSTS_INCLUDE_SUBDOMAINS = True

# Nombres con hash (embriolab.3f9a1c.css): el navegador nunca usa una versión vieja.
STORAGES = {
    **STORAGES,  # noqa: F405
    'staticfiles': {
        'BACKEND': 'django.contrib.staticfiles.storage.ManifestStaticFilesStorage',
    },
}

SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_SECURE = True

# La cuenta SMTP la entrega el cliente (semana 8).
MAILERS = {
    'default': {
        'BACKEND': 'django.core.mail.backends.smtp.EmailBackend',
        'OPTIONS': {
            'host': os.environ.get('EMAIL_HOST', ''),
            'port': int(os.environ.get('EMAIL_PORT', '587')),
            'username': os.environ.get('EMAIL_HOST_USER', ''),
            'password': os.environ.get('EMAIL_HOST_PASSWORD', ''),
            'use_tls': os.environ.get('EMAIL_USE_TLS', 'True') == 'True',
        },
    },
}

# Los links del formulario que salen por correo apuntan aquí.
if not os.environ.get('SITIO_URL'):
    raise ImproperlyConfigured('SITIO_URL es obligatorio en producción.')
