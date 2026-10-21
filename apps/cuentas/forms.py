from django import forms
from django.contrib.auth.forms import AuthenticationForm


class FormularioEntrar(AuthenticationForm):
    username = forms.EmailField(
        label='Correo electrónico',
        widget=forms.EmailInput(attrs={'autocomplete': 'email', 'autofocus': True}),
    )
    password = forms.CharField(
        label='Contraseña',
        strip=False,
        widget=forms.PasswordInput(attrs={'autocomplete': 'current-password'}),
    )

    error_messages = {
        'invalid_login': 'El correo o la contraseña no coinciden. Revíselos e intente de nuevo.',
        'inactive': 'Esta cuenta está desactivada. Consulte al administrador.',
    }
