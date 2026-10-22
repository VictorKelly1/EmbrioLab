"""
Una clase de Python por estudio (CONTEXTO.md §5). Importar este paquete las registra.

PROVISIONAL: glucosa, perfil de lípidos y espermatobioscopia son ejemplos mientras el
cliente entrega su Excel (claves, campos, fórmulas y casos reales para las pruebas).
"""

from apps.estudios.definiciones import espermatobioscopia, glucosa, perfil_lipidos  # noqa: F401
from apps.estudios.definiciones.base import REGISTRO, Campo, DefinicionEstudio, obtener, registrar

__all__ = ['REGISTRO', 'Campo', 'DefinicionEstudio', 'obtener', 'registrar']
