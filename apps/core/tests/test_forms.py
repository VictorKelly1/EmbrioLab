from django import forms
from django.core.exceptions import ValidationError

from apps.core.forms import aplicar_errores


class Formulario(forms.Form):
    curp = forms.CharField()


def _formulario():
    formulario = Formulario({'curp': 'X'})
    formulario.is_valid()
    return formulario


def test_errores_por_campo_y_generales():
    formulario = _formulario()
    aplicar_errores(formulario, ValidationError({'curp': 'Repetida.', 'otro': 'Falla.'}))
    assert formulario.errors['curp'] == ['Repetida.']
    assert formulario.non_field_errors() == ['Falla.']


def test_error_sin_campos():
    formulario = _formulario()
    aplicar_errores(formulario, ValidationError('Algo salió mal.'))
    assert formulario.non_field_errors() == ['Algo salió mal.']
