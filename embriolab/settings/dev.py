"""Settings de desarrollo local (Docker Compose o venv)."""

from .base import *  # noqa: F403
from .base import ALLOWED_HOSTS

DEBUG = True

if not ALLOWED_HOSTS:
    ALLOWED_HOSTS = ['localhost', '127.0.0.1']
