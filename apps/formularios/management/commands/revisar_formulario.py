"""
Revisa un archivo de formulario antes de publicarlo. Solo lee: no cambia la BD.

    manage.py revisar_formulario apps/formularios/datos/hombre_v2.json
    manage.py revisar_formulario apps/formularios/datos/hombre_v2.json --html vista.html

Dice si es válido, resume sus preguntas, compara con la versión publicada del mismo
género y, con --html, genera una vista previa de cómo lo verá el paciente en su celular
(un solo archivo que se abre en el navegador o se le manda al cliente).
"""

import re
from pathlib import Path

from django.contrib.staticfiles import finders
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.template.loader import render_to_string

from apps.formularios.carga import diferencias, formulario_de, leer
from apps.formularios.constructor import construir_formulario
from apps.formularios.models import Formulario

TIPOS = {
    'texto': 'texto',
    'texto_largo': 'texto largo',
    'numero': 'número',
    'si_no': 'sí/no',
    'opcion': 'una opción',
    'opciones': 'varias opciones',
    'fecha': 'fecha',
    'estudios': 'estudios del catálogo',
    'aceptacion': 'aceptación',
}
PARA = {'masculino': 'para hombres', 'femenino': 'para mujeres', '': 'para todos'}

AVISO = (
    '<p class="aviso" role="note" style="margin-bottom:1rem">'
    '<strong>Vista previa.</strong> Así verá el paciente el formulario. '
    'Las respuestas no se guardan.</p>'
)
SIN_ENVIO = (
    '<script>document.querySelector("form").addEventListener("submit", (e) => {'
    ' e.preventDefault(); alert("Vista previa: las respuestas no se guardan."); });</script>'
)


def vista_previa(esquema: dict) -> str:
    """La página pública con este esquema, en un solo HTML con el CSS incluido."""
    html = render_to_string(
        'formularios/publico.html',
        {
            'form': construir_formulario(esquema)(),
            # Sin petición no hay token; el envío de la vista previa está desactivado.
            'csrf_token': 'vista-previa',
        },
    )
    css = Path(finders.find('css/embriolab.css')).read_text(encoding='utf-8')
    # Sin archivos externos: el CSS va adentro; la fuente y htmx no hacen falta.
    html = re.sub(r'\s*<link rel="preload"[^>]*>', '', html)
    html = re.sub(r'\s*<script src="[^"]*htmx[^"]*"[^>]*></script>', '', html)
    html = re.sub(r'<link rel="stylesheet"[^>]*>', lambda _: f'<style>\n{css}\n</style>', html)
    html = html.replace(
        '<main class="publico__contenido">', f'<main class="publico__contenido">\n{AVISO}', 1
    )
    return html.replace('</body>', f'{SIN_ENVIO}\n</body>', 1)


class Command(BaseCommand):
    help = 'Valida un archivo de formulario, lo compara con lo publicado y genera una vista previa.'

    def add_arguments(self, parser):
        parser.add_argument('archivo', help='Ruta al JSON (apps/formularios/datos/…).')
        parser.add_argument('--html', metavar='RUTA', help='Escribe aquí la vista previa.')

    def handle(self, *args, archivo, html=None, **options):
        try:
            definicion = leer(archivo)
        except ValidationError as error:
            problemas = '\n'.join(f'  - {m}' for m in error.messages)
            raise CommandError(f'{Path(archivo).name} tiene problemas:\n{problemas}') from error

        escribir = self.stdout.write
        escribir(self.style.SUCCESS(f'{Path(archivo).name}: válido.'))
        escribir(f'«{definicion.nombre}», {PARA[definicion.genero_aplicable]}.')
        self._resumen(definicion.esquema)
        if 'pendientes' in Path(archivo).resolve().parts:
            escribir('\nArchivo pendiente: no lo publica ninguna migración; no se compara.')
        else:
            self._comparar(definicion)

        if html:
            Path(html).write_text(vista_previa(definicion.esquema), encoding='utf-8')
            escribir(f'\nVista previa: {Path(html).resolve()}')

    def _resumen(self, esquema):
        todas = [p for s in esquema['secciones'] for p in s['preguntas']]
        obligatorias = sum(bool(p.get('obligatoria')) for p in todas)
        condicionales = sum('mostrar_si' in p for p in todas)
        self.stdout.write(
            f'{len(esquema["secciones"])} secciones, {len(todas)} preguntas '
            f'({obligatorias} obligatorias, {condicionales} condicionales).\n'
        )
        for i, seccion in enumerate(esquema['secciones'], start=1):
            self.stdout.write(f'  {i}. {seccion["titulo"]}')
            for p in seccion['preguntas']:
                detalles = [TIPOS[p['tipo']]]
                if p.get('obligatoria'):
                    detalles.append('obligatoria')
                if 'mostrar_si' in p:
                    condicion = p['mostrar_si']
                    valor = condicion['valor']
                    if isinstance(valor, bool):
                        valor = 'sí' if valor else 'no'
                    detalles.append(f'si {condicion["clave"]} = {valor}')
                self.stdout.write(f'     - {p["clave"]} ({", ".join(detalles)}): {p["etiqueta"]}')

    def _comparar(self, definicion):
        escribir = self.stdout.write
        try:
            formulario = formulario_de(definicion, Formulario=Formulario)
        except ValidationError as error:
            raise CommandError(' '.join(error.messages)) from error
        actual = formulario and formulario.versiones.filter(publicada=True).first()
        if actual is None:
            escribir('\nNo hay formulario publicado para este género: publicarlo lo crea.')
            return
        escribir(
            f'\nFrente a lo publicado («{formulario.nombre}», versión {actual.numero_version}):'
        )
        if actual.esquema == definicion.esquema:
            escribir('  Sin cambios: publicarlo no crea una versión nueva.')
            return
        cambios = diferencias(actual.esquema, definicion.esquema)
        for signo, nombre, claves in (
            ('+', 'Agregadas', cambios.agregadas),
            ('-', 'Quitadas', cambios.quitadas),
            ('~', 'Cambiadas', cambios.cambiadas),
        ):
            if claves:
                escribir(f'  {signo} {nombre}: {", ".join(claves)}')
        if not cambios.hay:
            escribir('  Mismas preguntas; cambian títulos, descripciones u orden.')
        if cambios.quitadas or cambios.cambiadas:
            escribir(
                '  Las respuestas ya guardadas no cambian: conservan la versión con la que '
                'se llenaron.'
            )
