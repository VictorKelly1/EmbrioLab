from apps.core.texto import normalizar, sin_acentos


def test_sin_acentos():
    assert sin_acentos('Muñoz Pérez Ángel') == 'Munoz Perez Angel'


def test_normalizar():
    assert normalizar('  José   MARÍA\tÑúñez ') == 'jose maria nunez'
