from decimal import Decimal

from django import forms
from django.urls import reverse
from django.utils import timezone

from apps.cuentas.models import Quimico
from apps.estudios.definiciones import Campo
from apps.estudios.models import Estudio
from apps.pacientes.models import Doctor
from apps.pedidos.models import EstadoPago, EstadoPedido, EstudioPedido
from apps.pedidos.selectors import quimicos_activos
from apps.pedidos.services import Linea


class QuimicosField(forms.ModelMultipleChoiceField):
    """Uno o varios químicos responsables, como casillas."""

    widget = forms.CheckboxSelectMultiple

    def label_from_instance(self, quimico):
        return quimico.usuario.persona.nombre_completo


class EstudioField(forms.ModelChoiceField):
    def label_from_instance(self, estudio):
        return f'{estudio.nombre} ({estudio.clave})'


def _estudios():
    return Estudio.objects.filter(activo=True).order_by('nombre')


class LineaForm(forms.Form):
    """Un estudio de la orden. El nombre de la orden alimenta las sugerencias."""

    nombre_solicitado = forms.CharField(
        label='Nombre en la orden',
        max_length=150,
        required=False,
        help_text='Como lo escribió el doctor. Vacío = el nombre del catálogo.',
        widget=forms.TextInput(attrs={'autocomplete': 'off', 'data-nombre-solicitado': ''}),
    )
    estudio = EstudioField(
        label='Estudio del catálogo',
        queryset=Estudio.objects.none(),
        empty_label='Elija un estudio',
        widget=forms.Select(attrs={'data-estudio': ''}),
    )
    guardar_alias = forms.BooleanField(
        label='Guardar el nombre como alias de este estudio', required=False
    )
    quimicos = QuimicosField(
        label='Químicos responsables',
        queryset=None,
        required=False,
        help_text='Puede elegir uno o varios. Sin químico, el estudio queda pendiente.',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['estudio'].queryset = _estudios()
        self.fields['quimicos'].queryset = quimicos_activos()
        self.fields['nombre_solicitado'].widget.attrs.update(
            {
                'hx-get': reverse('pedidos:sugerencias'),
                'hx-trigger': 'input changed delay:300ms',
                'hx-target': 'next [data-sugerencias]',
                'hx-sync': 'this:replace',
            }
        )

    def linea(self) -> Linea:
        datos = self.cleaned_data
        return Linea(
            estudio=datos['estudio'],
            nombre_solicitado=datos['nombre_solicitado'],
            guardar_alias=datos['guardar_alias'],
            quimicos=tuple(datos['quimicos']),
        )


LineaFormSet = forms.formset_factory(LineaForm, extra=0, min_num=1, validate_min=True)


class DoctorPedidoForm(forms.Form):
    doctor = forms.ModelChoiceField(
        label='Doctor que firma la orden',
        queryset=Doctor.objects.all(),
        required=False,
        empty_label='Sin doctor',
    )


class EstudioPedidoForm(forms.Form):
    """La fila de un estudio en el detalle del pedido."""

    quimicos = QuimicosField(label='Químicos', queryset=None, required=False)
    estado_pago = forms.ChoiceField(label='Pago', choices=EstadoPago.choices)

    def __init__(self, *args, quimicos_asignados=(), **kwargs):
        super().__init__(*args, **kwargs)
        # Los activos más los ya asignados, aunque se hayan dado de baja después.
        activos = quimicos_activos()
        asignados = activos.model.objects.filter(pk__in=[q.pk for q in quimicos_asignados])
        self.fields['quimicos'].queryset = (activos | asignados).distinct()


class PagoPedidoForm(forms.Form):
    estado_pago = forms.ChoiceField(choices=EstadoPago.choices)


class EstudiosEnvioField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, obj):
        if obj.enviado:
            fecha = timezone.localtime(obj.fecha_envio)
            return f'{obj.estudio.nombre} (enviado el {fecha:%d/%m/%Y})'
        return obj.estudio.nombre


class EnviarResultadosForm(forms.Form):
    """Los estudios completados del pedido que se envían juntos."""

    estudios = EstudiosEnvioField(
        queryset=EstudioPedido.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        error_messages={'required': 'Elija al menos un estudio para enviar.'},
    )

    def __init__(self, *args, completados, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['estudios'].queryset = completados


class QuimicoField(forms.ModelChoiceField):
    def label_from_instance(self, quimico):
        return quimico.usuario.persona.nombre_completo


class FiltroPedidosForm(forms.Form):
    q = forms.CharField(label='Buscar por número, folio o paciente', required=False)
    estado = forms.ChoiceField(
        label='Estado',
        required=False,
        choices=[('', 'Todos'), *EstadoPedido.choices],
    )
    estado_pago = forms.ChoiceField(
        label='Pago', required=False, choices=[('', 'Todos'), *EstadoPago.choices]
    )
    # Todos, no solo los activos: el historial incluye a los que se dieron de baja.
    quimico = QuimicoField(
        label='Químico asignado',
        required=False,
        empty_label='Todos',
        queryset=Quimico.objects.select_related('usuario__persona').order_by(
            'usuario__persona__nombre', 'usuario__persona__apellido_paterno'
        ),
    )
    desde = forms.DateField(
        label='Desde', required=False, widget=forms.DateInput(attrs={'type': 'date'})
    )
    hasta = forms.DateField(
        label='Hasta', required=False, widget=forms.DateInput(attrs={'type': 'date'})
    )

    def clean(self):
        datos = super().clean()
        desde, hasta = datos.get('desde'), datos.get('hasta')
        if desde and hasta and desde > hasta:
            self.add_error('hasta', 'Debe ser igual o posterior a «Desde».')
        return datos


def _campo_resultado(campo: Campo, requerido: bool) -> forms.Field:
    comunes = {'label': campo.etiqueta, 'required': requerido, 'help_text': campo.unidad}
    if campo.tipo in ('decimal', 'entero'):
        limites = {'min_value': campo.minimo, 'max_value': campo.maximo}
        decimales = campo.decimales if campo.tipo == 'decimal' else 0
        atributos = {'inputmode': 'decimal' if decimales else 'numeric', 'autocomplete': 'off'}
        atributos['step'] = str(Decimal(1).scaleb(-decimales)) if decimales else '1'
        if campo.tipo == 'entero':
            return forms.IntegerField(
                widget=forms.NumberInput(attrs=atributos), **limites, **comunes
            )
        return forms.DecimalField(
            decimal_places=decimales,
            widget=forms.NumberInput(attrs=atributos),
            **limites,
            **comunes,
        )
    if campo.tipo == 'opcion':
        opciones = [('', 'Elija una opción'), *((o, o) for o in campo.opciones)]
        return forms.ChoiceField(choices=opciones, **comunes)
    return forms.CharField(max_length=500, **comunes)


class ResultadosForm(forms.Form):
    """
    Captura de un estudio, generada desde los `campos` de su definición. Para un borrador
    nada es obligatorio; para completar, todos.
    """

    def __init__(self, *args, definicion, completar: bool = False, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in definicion.campos:
            self.fields[campo.clave] = _campo_resultado(campo, completar)

    def valores(self) -> dict:
        return {
            clave: valor.strip() if isinstance(valor, str) else valor
            for clave, valor in self.cleaned_data.items()
        }
