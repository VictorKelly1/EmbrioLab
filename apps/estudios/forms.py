from django import forms
from django.utils import timezone

from apps.estudios.models import Estudio
from apps.personas.models import Genero


class AliasForm(forms.Form):
    alias = forms.CharField(
        label='Nombre que usa el doctor',
        max_length=150,
        help_text='Tal como viene en la orden. Se guarda sin acentos ni mayúsculas.',
    )
    estudio = forms.ModelChoiceField(
        label='Estudio del catálogo',
        queryset=Estudio.objects.filter(activo=True).select_related('categoria'),
    )


class ValorReferenciaForm(forms.Form):
    clave_campo = forms.ChoiceField(label='Campo')
    genero = forms.ChoiceField(
        label='Aplica a', choices=[('', 'Hombres y mujeres'), *Genero.choices], required=False
    )
    edad_minima = forms.IntegerField(
        label='Edad mínima', min_value=0, max_value=150, required=False
    )
    edad_maxima = forms.IntegerField(
        label='Edad máxima', min_value=0, max_value=150, required=False
    )
    valor_minimo = forms.DecimalField(
        label='Valor mínimo', max_digits=12, decimal_places=4, required=False
    )
    valor_maximo = forms.DecimalField(
        label='Valor máximo', max_digits=12, decimal_places=4, required=False
    )
    texto_referencia = forms.CharField(
        label='Texto de referencia',
        max_length=200,
        required=False,
        help_text='Para resultados que no son números, por ejemplo «Negativo».',
    )
    unidad = forms.CharField(
        max_length=30, required=False, help_text='Vacío = la unidad del campo.'
    )
    vigente_desde = forms.DateField(
        label='Vigente desde',
        initial=timezone.localdate,
        widget=forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
    )

    def __init__(self, *args, estudio: Estudio, **kwargs):
        super().__init__(*args, **kwargs)
        definicion = estudio.definicion
        campos = definicion.todos_los_campos() if definicion else ()
        self.fields['clave_campo'].choices = [
            (c.clave, f'{c.etiqueta} ({c.unidad})' if c.unidad else c.etiqueta) for c in campos
        ]
        for edad in ('edad_minima', 'edad_maxima'):
            self.fields[edad].help_text = 'En años. Vacío = sin límite.'
