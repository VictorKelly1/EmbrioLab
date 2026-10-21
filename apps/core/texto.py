"""Utilidades de texto compartidas por el dominio."""

import unicodedata


def sin_acentos(texto: str) -> str:
    """'Muñoz Pérez' → 'Munoz Perez'."""
    descompuesto = unicodedata.normalize('NFKD', texto)
    return ''.join(c for c in descompuesto if not unicodedata.combining(c))


def normalizar(texto: str) -> str:
    """Forma para buscar y comparar: sin acentos, en minúsculas y con espacios simples."""
    return ' '.join(sin_acentos(texto).lower().split())
