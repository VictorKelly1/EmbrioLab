from django import forms
from django.contrib.auth.forms import AuthenticationForm

from apps.cuentas.models import Rol
from apps.personas.models import Genero


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


class UsuarioForm(forms.Form):
    """Alta de personal por el administrador: datos de la persona, acceso y rol."""

    nombre = forms.CharField(label='Nombre(s)', max_length=100)
    apellido_paterno = forms.CharField(max_length=100)
    apellido_materno = forms.CharField(max_length=100, required=False)
    genero = forms.ChoiceField(label='Género', choices=Genero.choices, widget=forms.RadioSelect)
    fecha_nacimiento = forms.DateField(
        label='Fecha de nacimiento',
        widget=forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
    )
    curp = forms.CharField(
        label='CURP',
        max_length=18,
        widget=forms.TextInput(attrs={'autocapitalize': 'characters', 'spellcheck': 'false'}),
    )

    rol = forms.ChoiceField(choices=Rol.choices, widget=forms.RadioSelect)
    cedula_profesional = forms.CharField(
        label='Cédula profesional',
        max_length=20,
        required=False,
        help_text='Obligatoria para químicos.',
    )
    sueldo = forms.DecimalField(max_digits=10, decimal_places=2, min_value=0)
    color = forms.CharField(
        max_length=7,
        initial='#B57EDC',
        widget=forms.TextInput(attrs={'type': 'color'}),
        help_text='Identifica al usuario en el calendario y los pedidos.',
    )

    correo = forms.EmailField(
        label='Correo electrónico', help_text='Con este correo inicia sesión.'
    )
    password = forms.CharField(
        label='Contraseña inicial',
        strip=False,
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}),
    )
    password_confirmacion = forms.CharField(
        label='Repita la contraseña',
        strip=False,
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}),
    )

    secciones = (
        (
            'Datos de la persona',
            (
                'nombre',
                'apellido_paterno',
                'apellido_materno',
                'genero',
                'fecha_nacimiento',
                'curp',
            ),
        ),
        ('Puesto', ('rol', 'cedula_profesional', 'sueldo', 'color')),
        ('Acceso', ('correo', 'password', 'password_confirmacion')),
    )

    @property
    def grupos(self):
        return [(titulo, [self[c] for c in campos]) for titulo, campos in self.secciones]

    def clean(self):
        datos = super().clean()
        password = datos.get('password')
        if password and password != datos.get('password_confirmacion'):
            self.add_error('password_confirmacion', 'Las contraseñas no coinciden.')
        return datos

    def datos_servicio(self) -> dict:
        """Argumentos para cuentas.services.registrar_usuario."""
        datos = self.cleaned_data
        return {
            'datos_persona': {
                c: datos[c]
                for c in (
                    'nombre',
                    'apellido_paterno',
                    'apellido_materno',
                    'genero',
                    'fecha_nacimiento',
                    'curp',
                )
            },
            'correo': datos['correo'],
            'password': datos['password'],
            'rol': datos['rol'],
            'sueldo': datos['sueldo'],
            'cedula_profesional': datos['cedula_profesional'],
            'color': datos['color'],
        }
