import datetime

from django import forms
from django.utils import timezone

from apps.pacientes.models import Paciente


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


class CitaForm(_ConPaciente, _ConFechaHora):
    asunto = forms.CharField(
        max_length=200,
        required=False,
        help_text='Opcional. Por ejemplo, el estudio que viene a realizarse.',
    )

    field_order = ['paciente', 'fecha', 'hora', 'asunto']


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
