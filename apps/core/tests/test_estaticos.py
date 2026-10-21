from django.template import Context, Template


def _render(debug, settings):
    settings.DEBUG = debug
    plantilla = Template("{% load estaticos %}{% estatico 'css/embriolab.css' %}")
    return plantilla.render(Context())


def test_en_desarrollo_agrega_version(settings):
    assert _render(True, settings).startswith('/static/css/embriolab.css?v=')


def test_sin_debug_usa_la_url_del_almacenamiento(settings):
    assert _render(False, settings) == '/static/css/embriolab.css'
