"""Genera un forms.Form a partir de un esquema validado (ver esquema.py)."""

import datetime
from decimal import Decimal

from django import forms
from django.utils import timezone

from apps.formularios.esquema import preguntas

SI_NO = [('si', 'Sí'), ('no', 'No')]


def _campo(pregunta: dict) -> forms.Field:
    tipo = pregunta['tipo']
    comunes = {
        'label': pregunta['etiqueta'],
        'help_text': pregunta.get('ayuda', ''),
        # Las condicionales se exigen en clean(), solo si se muestran.
        'required': pregunta.get('obligatoria', False) and 'mostrar_si' not in pregunta,
    }
    if tipo == 'texto':
        return forms.CharField(max_length=500, **comunes)
    if tipo == 'texto_largo':
        return forms.CharField(max_length=2000, widget=forms.Textarea(attrs={'rows': 3}), **comunes)
    if tipo == 'numero':
        decimales = pregunta.get('decimales', 0)
        limites = {'min_value': pregunta.get('min'), 'max_value': pregunta.get('max')}
        atributos = {'inputmode': 'decimal' if decimales else 'numeric'}
        if decimales:
            atributos['step'] = str(Decimal(1).scaleb(-decimales))
            return forms.DecimalField(
                decimal_places=decimales,
                widget=forms.NumberInput(attrs=atributos),
                **limites,
                **comunes,
            )
        return forms.IntegerField(widget=forms.NumberInput(attrs=atributos), **limites, **comunes)
    if tipo == 'si_no':
        return forms.ChoiceField(choices=SI_NO, widget=forms.RadioSelect, **comunes)
    if tipo == 'opcion':
        opciones = [(o, o) for o in pregunta['opciones']]
        return forms.ChoiceField(choices=opciones, widget=forms.RadioSelect, **comunes)
    if tipo == 'opciones':
        opciones = [(o, o) for o in pregunta['opciones']]
        return forms.MultipleChoiceField(
            choices=opciones, widget=forms.CheckboxSelectMultiple, **comunes
        )
    if tipo == 'fecha':
        atributos = {'type': 'date'}
        if pregunta.get('no_futura'):
            atributos['max'] = timezone.localdate().isoformat()
        return forms.DateField(widget=forms.DateInput(attrs=atributos), **comunes)
    raise ValueError(f'Tipo desconocido: {tipo}')


def _a_json(pregunta: dict, valor):
    """Valor limpio del form → valor que se guarda en las respuestas."""
    tipo = pregunta['tipo']
    if valor in (None, '', []):
        return None
    if tipo == 'si_no':
        return valor == 'si'
    if tipo == 'numero':
        return float(valor) if isinstance(valor, Decimal) else valor
    if tipo == 'fecha':
        return valor.isoformat()
    if isinstance(valor, str):
        return valor.strip() or None
    return valor


class FormularioDinamico(forms.Form):
    esquema: dict = {}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._preguntas = {p['clave']: p for p in preguntas(self.esquema)}
        for clave, pregunta in self._preguntas.items():
            self.fields[clave] = _campo(pregunta)

    def _se_muestra(self, pregunta: dict, valores: dict) -> bool:
        condicion = pregunta.get('mostrar_si')
        if not condicion:
            return True
        origen = self._preguntas[condicion['clave']]
        if not self._se_muestra(origen, valores):
            return False
        return valores.get(condicion['clave']) == condicion['valor']

    def clean(self):
        datos = super().clean()
        valores = {
            clave: _a_json(pregunta, datos.get(clave))
            for clave, pregunta in self._preguntas.items()
        }
        for clave, pregunta in self._preguntas.items():
            if not self._se_muestra(pregunta, valores):
                valores[clave] = None
                self.errors.pop(clave, None)
            elif (
                pregunta.get('obligatoria') and valores[clave] is None and clave not in self.errors
            ):
                self.add_error(clave, 'Este campo es obligatorio.')
        self._respuestas = {c: v for c, v in valores.items() if v is not None}
        return datos

    def respuestas(self) -> dict:
        """Respuestas listas para guardar en JSON. Llamar tras is_valid()."""
        return self._respuestas

    @property
    def secciones(self):
        """Para la plantilla: secciones con sus campos y la condición para mostrarlos."""
        resultado = []
        for seccion in self.esquema['secciones']:
            campos = []
            for pregunta in seccion['preguntas']:
                condicion = pregunta.get('mostrar_si')
                campos.append(
                    {
                        'campo': self[pregunta['clave']],
                        'condicion_clave': condicion['clave'] if condicion else '',
                        'condicion_valor': _valor_html(condicion['valor']) if condicion else '',
                    }
                )
            resultado.append(
                {
                    'titulo': seccion['titulo'],
                    'descripcion': seccion.get('descripcion', ''),
                    'campos': campos,
                }
            )
        return resultado


def _valor_html(valor) -> str:
    """Valor de la condición tal como llega del navegador ('si'/'no' o el texto)."""
    if isinstance(valor, bool):
        return 'si' if valor else 'no'
    return str(valor)


def construir_formulario(esquema: dict) -> type[FormularioDinamico]:
    return type('Formulario', (FormularioDinamico,), {'esquema': esquema})


def respuestas_legibles(esquema: dict, respuestas: dict) -> list[dict]:
    """[{seccion, etiqueta, valor}] en el orden del esquema, solo lo respondido."""
    legibles = []
    for seccion in esquema['secciones']:
        for pregunta in seccion['preguntas']:
            if pregunta['clave'] not in respuestas:
                continue
            valor = respuestas[pregunta['clave']]
            if isinstance(valor, bool):
                valor = 'Sí' if valor else 'No'
            elif isinstance(valor, list):
                valor = ', '.join(valor)
            elif pregunta['tipo'] == 'fecha':
                valor = datetime.date.fromisoformat(valor).strftime('%d/%m/%Y')
            elif isinstance(valor, float) and valor.is_integer():
                valor = int(valor)
            legibles.append(
                {'seccion': seccion['titulo'], 'etiqueta': pregunta['etiqueta'], 'valor': valor}
            )
    return legibles
