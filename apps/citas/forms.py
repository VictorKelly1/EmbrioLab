import datetime

from django import forms
from django.utils import timezone

from apps.citas.services import SinRegistro
from apps.pacientes.models import Paciente
from apps.personas.models import Genero


def _fecha_hora(fecha: datetime.date, hora: datetime.time) -> datetime.datetime:
    return timezone.make_aware(datetime.datetime.combine(fecha, hora))


class _ConPaciente(forms.Form):
    # Se llena con el buscador (HTMX); solo pacientes activos.
    paciente = forms.ModelChoiceField(
        queryset=Paciente.objects.activos().select_related('persona'),
        widget=forms.HiddenInput,
        error_messages={
            'required': 'Busque y elija al paciente.',
            'invalid_choice': 'Elija un paciente activo de la lista.',
        },
    )


class _ConFechaHora(forms.Form):
    fecha = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'))
    hora = forms.TimeField(widget=forms.TimeInput(attrs={'type': 'time'}, format='%H:%M'))

    def fecha_hora(self) -> datetime.datetime:
        return _fecha_hora(self.cleaned_data['fecha'], self.cleaned_data['hora'])


class TipoPaciente:
    REGISTRADO = 'registrado'
    SIN_REGISTRO = 'sin_registro'


class CitaForm(_ConPaciente, _ConFechaHora):
    """
    Con un paciente registrado o, si aún no lo está, con sus datos mínimos
    (CONTEXTO.md §3). El servicio vuelve a validar los datos sin registro.
    """

    tipo = forms.ChoiceField(
        label='¿El paciente ya está registrado?',
        choices=[
            (TipoPaciente.REGISTRADO, 'Sí, buscarlo'),
            (TipoPaciente.SIN_REGISTRO, 'No, todavía no'),
        ],
        initial=TipoPaciente.REGISTRADO,
        required=False,  # sin elegir = registrado
        widget=forms.RadioSelect,
    )
    nombre = forms.CharField(label='Nombre', max_length=100, required=False)
    apellido_paterno = forms.CharField(label='Apellido paterno', max_length=100, required=False)
    genero = forms.ChoiceField(
        label='Género',
        choices=[('', 'Elija…'), *Genero.choices],
        required=False,
        help_text='Con él se elige el formulario de la visita.',
    )
    telefono = forms.CharField(
        label='Teléfono (WhatsApp)',
        max_length=16,
        required=False,
        widget=forms.TextInput(attrs={'inputmode': 'tel', 'autocomplete': 'off'}),
        help_text='Escriba un teléfono o un correo para el recordatorio.',
    )
    correo = forms.EmailField(
        label='Correo',
        required=False,
        error_messages={'invalid': 'Escriba un correo válido.'},
    )
    asunto = forms.CharField(
        max_length=200,
        required=False,
        help_text='Opcional. Por ejemplo, el estudio que viene a realizarse.',
    )

    field_order = [
        'tipo',
        'paciente',
        'nombre',
        'apellido_paterno',
        'genero',
        'telefono',
        'correo',
        'fecha',
        'hora',
        'asunto',
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Se exige según el tipo, en clean().
        self.fields['paciente'].required = False
        # Obligatorios solo sin registro (los revisa el servicio); la plantilla pone el *.
        for campo in ('nombre', 'apellido_paterno', 'genero'):
            self.fields[campo].obligatoria_si_se_muestra = True

    @property
    def sin_registro(self) -> bool:
        return self['tipo'].value() == TipoPaciente.SIN_REGISTRO

    def clean(self):
        datos = super().clean()
        datos['tipo'] = datos.get('tipo') or TipoPaciente.REGISTRADO
        if datos['tipo'] == TipoPaciente.SIN_REGISTRO:
            datos['paciente'] = None
        elif not datos.get('paciente') and 'paciente' not in self.errors:
            self.add_error('paciente', 'Busque y elija al paciente.')
        return datos

    def datos_servicio(self) -> dict:
        datos = self.cleaned_data
        if datos['tipo'] == TipoPaciente.REGISTRADO:
            return {'paciente': datos['paciente']}
        return {
            'sin_registro': SinRegistro(
                nombre=datos['nombre'],
                apellido_paterno=datos['apellido_paterno'],
                genero=datos['genero'],
                telefono=datos['telefono'],
                correo=datos['correo'],
            )
        }


class LlegadaForm(_ConPaciente):
    """Liga la cita sin registro a un paciente que ya existe."""


class EspontaneaForm(_ConPaciente):
    hora = forms.TimeField(
        label='Hora de llegada',
        widget=forms.TimeInput(attrs={'type': 'time'}, format='%H:%M'),
        help_text='Por defecto, la hora actual.',
    )
    asunto = forms.CharField(max_length=200, required=False)

    def fecha_hora(self) -> datetime.datetime:
        return _fecha_hora(timezone.localdate(), self.cleaned_data['hora'])


class ReprogramarForm(_ConFechaHora):
    pass
