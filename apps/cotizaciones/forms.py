from django import forms
from django.core.validators import RegexValidator

from apps.cotizaciones.cotizacion import EstudioLibre
from apps.estudios.models import CategoriaEstudio, Estudio
from apps.pacientes.models import Paciente
from apps.personas.models import TELEFONO_REGEX


class EstudiosField(forms.ModelMultipleChoiceField):
    widget = forms.CheckboxSelectMultiple

    def label_from_instance(self, estudio):
        return estudio.nombre


class EstudioLibreForm(forms.Form):
    """Un estudio que no está en el catálogo: nombre, precio y, si se quiere, categoría."""

    nombre = forms.CharField(label='Nombre', max_length=150)
    precio = forms.DecimalField(
        label='Precio',
        min_value=0,
        max_digits=10,
        decimal_places=2,
        error_messages={'min_value': 'El precio no puede ser negativo.'},
        widget=forms.NumberInput(attrs={'step': '0.01', 'min': '0', 'inputmode': 'decimal'}),
    )
    categoria = forms.ModelChoiceField(
        label='Categoría',
        queryset=CategoriaEstudio.objects.all(),
        required=False,
        empty_label='—',
        to_field_name='nombre',
    )

    def libre(self) -> EstudioLibre:
        datos = self.cleaned_data
        categoria = datos.get('categoria')
        return EstudioLibre(datos['nombre'], datos['precio'], categoria.nombre if categoria else '')


# Las filas se agregan en el navegador; una fila vacía se ignora.
EstudioLibreFormSet = forms.formset_factory(EstudioLibreForm, extra=0)


def estudios_activos():
    return Estudio.objects.filter(activo=True).select_related('categoria')


class CotizacionForm(forms.Form):
    """El paquete de estudios y, para enviarla, a quién. Nada de esto se guarda."""

    # Opcional: también se puede cotizar solo con estudios libres; cotizar() pide al menos uno.
    estudios = EstudiosField(queryset=Estudio.objects.none(), required=False)
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
