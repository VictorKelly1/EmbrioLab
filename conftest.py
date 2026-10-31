import pytest


@pytest.fixture(autouse=True)
def _almacenamiento_privado_temporal(settings, tmp_path):
    """Las pruebas nunca escriben en la carpeta privada real."""
    settings.STORAGES = {
        **settings.STORAGES,
        'privado': {
            'BACKEND': 'apps.core.almacenamiento.AlmacenamientoPrivado',
            'OPTIONS': {'location': tmp_path / 'privado'},
        },
    }


@pytest.fixture(autouse=True)
def _tareas_inmediatas(settings):
    """
    Las tareas corren en el mismo proceso al encolarse, sin worker. Como se encolan con
    `on_commit`, una prueba que quiera ejecutarlas usa `django_capture_on_commit_callbacks`.
    """
    settings.TASKS = {'default': {'BACKEND': 'django.tasks.backends.immediate.ImmediateBackend'}}


@pytest.fixture
def imagen_png():
    """Una imagen PNG válida de 1×1 px, como archivo subido."""
    import io

    from django.core.files.uploadedfile import SimpleUploadedFile
    from PIL import Image

    buffer = io.BytesIO()
    Image.new('RGB', (1, 1), '#b57edc').save(buffer, format='PNG')
    return SimpleUploadedFile('foto de Ana López.png', buffer.getvalue(), 'image/png')
