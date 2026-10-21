"""
Regla del folio del paciente (CONTEXTO.md §3), aislada aquí para poder cambiarla.

Folio = 2 primeras letras del apellido paterno + 2 del materno + número de paciente.
Es el mismo en todas las citas del paciente.
"""

import re

from apps.core.texto import sin_acentos

# PROVISIONAL: la regla para quien no tiene apellido materno la decide el cliente
# (CONTEXTO.md §8). Mientras tanto se rellena con X, como hace la CURP.
RELLENO = 'X'


def _dos_letras(apellido: str) -> str:
    letras = re.sub(r'[^A-Z]', '', sin_acentos(apellido).upper())
    return letras[:2].ljust(2, RELLENO)


def generar_folio(apellido_paterno: str, apellido_materno: str, numero: int) -> str:
    """generar_folio('López', 'García', 15) → 'LOGA15'."""
    return f'{_dos_letras(apellido_paterno)}{_dos_letras(apellido_materno)}{numero}'
