from django import forms
from django.core.validators import RegexValidator

from apps.estudios.models import Estudio
from apps.pacientes.models import Paciente
from apps.personas.models import TELEFONO_REGEX


class EstudiosField(forms.ModelMultipleChoiceField):
    widget = forms.CheckboxSelectMultiple

    def label_from_instance(self, estudio):
        return estudio.nombre


def estudios_activos():
    return Estudio.objects.filter(activo=True).select_related('categoria')


class CotizacionForm(forms.Form):
    """El paquete de estudios y, para enviarla, a quién. Nada de esto se guarda."""

    estudios = EstudiosField(
        queryset=Estudio.objects.none(),
        error_messages={'required': 'Elija al menos un estudio para cotizar.'},
    )
    # Se llena con el buscador de pacientes (HTMX); opcional.
    paciente = forms.ModelChoiceField(
        queryset=Paciente.objects.filter(estado_actividad=True).select_related('persona'),
        required=False,
        widget=forms.HiddenInput,
        error_messages={'invalid_choice': 'Elija un paciente activo de la lista.'},
    )
    cliente = forms.CharField(
        label='Nombre en la cotización',
        max_length=150,
        required=False,
        help_text='Si eligió un paciente, se usa su nombre.',
    )
    correo = forms.EmailField(
        label='Correo',
        required=False,
        error_messages={'invalid': 'Escriba un correo válido.'},
    )
    whatsapp = forms.CharField(
        label='WhatsApp',
        max_length=16,
        required=False,
        validators=[
            RegexValidator(
                TELEFONO_REGEX, 'Escriba el número con lada: 10 dígitos (o +código de país).'
            )
        ],
        widget=forms.TextInput(attrs={'inputmode': 'tel', 'autocomplete': 'off'}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['estudios'].queryset = estudios_activos()

    def nombre_cliente(self) -> str:
        paciente = self.cleaned_data.get('paciente')
        if paciente is not None:
            return paciente.persona.nombre_completo
        return self.cleaned_data.get('cliente', '')

    def estudios_en_orden(self) -> list:
        """En el orden del catálogo (categoría y nombre), no en el que se marcaron."""
        return sorted(self.cleaned_data['estudios'], key=lambda e: (e.categoria.nombre, e.nombre))
