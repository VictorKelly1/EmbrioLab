import pytest

from apps.pacientes.folio import generar_folio


@pytest.mark.parametrize(
    ('paterno', 'materno', 'numero', 'folio'),
    [
        ('López', 'García', 15, 'LOGA15'),
        ('Ávila', 'Ortiz', 7, 'AVOR7'),
        ('Muñoz', 'Núñez', 120, 'MUNU120'),
        ('de la Cruz', 'Pérez', 3, 'DEPE3'),
        ('O', 'Íñiguez', 1, 'OXIN1'),
    ],
)
def test_dos_letras_de_cada_apellido_y_numero(paterno, materno, numero, folio):
    assert generar_folio(paterno, materno, numero) == folio


def test_sin_apellido_materno_provisional():
    # Regla provisional hasta que decida el cliente (CONTEXTO.md §8).
    assert generar_folio('López', '', 15) == 'LOXX15'
