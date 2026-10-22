"""Token del link/QR del formulario: aleatorio, solo su hash en la BD (CONTEXTO.md §5)."""

import hashlib
import secrets


def nuevo_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
