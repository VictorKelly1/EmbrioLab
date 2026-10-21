import datetime

from django import forms
from django.core.validators import RegexValidator

from apps.personas.models import CURP_REGEX, TELEFONO_REGEX, Genero, TipoContacto
from apps.personas.selectors import contactos_principales
from apps.personas.services import CAMPOS_DIRECCION, CAMPOS_PERSONA

FOTO_TAMANO_MAXIMO = 5 * 1024 * 1024  # 5 MB

CAMPOS_CONTACTO = tuple(TipoContacto.values)

_telefono = RegexValidator(
    TELEFONO_REGEX, 'Escriba el número con lada: 10 dígitos (o +código de país).'
)


def _sin_separadores(valor: str) -> str:
    return ''.join(c for c in valor if c not in ' -().')


class PacienteForm(forms.Form):
    # Identidad
    nombre = forms.CharField(label='Nombre(s)', max_length=100)
    apellido_paterno = forms.CharField(max_length=100)
    apellido_materno = forms.CharField(
        max_length=100, required=False, help_text='Déjelo vacío si no tiene.'
    )
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
    numero_ine = forms.CharField(label='Número de INE', max_length=20, required=False)
    # FileInput y no ClearableFileInput: la foto es privada y no tiene URL que mostrar.
    foto = forms.ImageField(
        required=False,
        widget=forms.FileInput(attrs={'accept': 'image/*'}),
        help_text='JPG o PNG, máximo 5 MB.',
    )
    quitar_foto = forms.BooleanField(label='Quitar la foto actual', required=False)

    # Contacto
    whatsapp = forms.CharField(
        label='WhatsApp',
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={'inputmode': 'tel', 'autocomplete': 'off'}),
    )
    telefono = forms.CharField(
        label='Teléfono',
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={'inputmode': 'tel', 'autocomplete': 'off'}),
    )
    correo = forms.EmailField(label='Correo electrónico', required=False)

    # Dirección (opcional)
    calle = forms.CharField(max_length=150, required=False)
    numero = forms.CharField(label='Número', max_length=20, required=False)
    colonia_frac = forms.CharField(
        label='Colonia o fraccionamiento', max_length=150, required=False
    )
    ciudad = forms.CharField(max_length=100, required=False)
    estado = forms.CharField(max_length=100, required=False)
    pais = forms.CharField(label='País', max_length=100, required=False, initial='México')
    codigo_postal = forms.CharField(label='Código postal', max_length=10, required=False)

    secciones = (
        ('Datos del paciente', CAMPOS_PERSONA + ('foto', 'quitar_foto')),
        ('Contacto', CAMPOS_CONTACTO),
        ('Dirección', CAMPOS_DIRECCION),
    )

    def clean_curp(self):
        curp = self.cleaned_data['curp'].strip().upper()
        RegexValidator(CURP_REGEX, 'Revise la CURP: debe tener 18 caracteres válidos.')(curp)
        return curp

    def clean_fecha_nacimiento(self):
        fecha = self.cleaned_data['fecha_nacimiento']
        if fecha > datetime.date.today():
            raise forms.ValidationError('La fecha de nacimiento no puede ser futura.')
        return fecha

    def clean_foto(self):
        foto = self.cleaned_data.get('foto')
        if foto and getattr(foto, 'size', 0) > FOTO_TAMANO_MAXIMO:
            raise forms.ValidationError('La foto pesa más de 5 MB.')
        return foto

    def _clean_telefono(self, campo):
        valor = _sin_separadores(self.cleaned_data[campo].strip())
        if valor:
            _telefono(valor)
        return valor

    def clean_whatsapp(self):
        return self._clean_telefono('whatsapp')

    def clean_telefono(self):
        return self._clean_telefono('telefono')

    def __init__(self, *args, tiene_foto=False, **kwargs):
        super().__init__(*args, **kwargs)
        if not tiene_foto:
            del self.fields['quitar_foto']

    @property
    def grupos(self):
        """Campos agrupados por sección, para la plantilla."""
        return [
            (titulo, [self[c] for c in campos if c in self.fields])
            for titulo, campos in self.secciones
        ]

    def datos_servicio(self) -> dict:
        """Argumentos para registrar_paciente / actualizar_paciente."""
        datos = self.cleaned_data
        foto = False if datos.get('quitar_foto') else datos.get('foto')
        return {
            'datos_persona': {c: datos[c] for c in CAMPOS_PERSONA},
            'contactos': {c: datos[c] for c in CAMPOS_CONTACTO},
            'direccion': {c: datos[c] for c in CAMPOS_DIRECCION},
            'foto': foto,  # None = sin cambios, False = quitar
        }

    @classmethod
    def inicial_de(cls, paciente) -> dict:
        persona = paciente.persona
        inicial = {c: getattr(persona, c) for c in CAMPOS_PERSONA}
        inicial.update(contactos_principales(persona))
        if persona.direccion:
            inicial.update({c: getattr(persona.direccion, c) for c in CAMPOS_DIRECCION})
        return inicial


class DoctorForm(forms.Form):
    nombre = forms.CharField(max_length=200)
    contacto = forms.CharField(
        max_length=200, required=False, help_text='Teléfono, correo o consultorio.'
    )
