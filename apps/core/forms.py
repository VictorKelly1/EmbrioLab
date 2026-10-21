from django import forms
from django.core.exceptions import ValidationError


def aplicar_errores(formulario: forms.Form, error: ValidationError) -> None:
    """Pasa los errores de un servicio al formulario: a su campo si existe, si no, generales."""
    if not hasattr(error, 'error_dict'):
        formulario.add_error(None, error)
        return
    for campo, mensajes in error.message_dict.items():
        destino = campo if campo in formulario.fields else None
        for mensaje in mensajes:
            formulario.add_error(destino, mensaje)
