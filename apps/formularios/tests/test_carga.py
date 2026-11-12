"""Formularios desde archivos JSON: leer, publicar (también en migraciones) y revisar."""

import copy
import json
import re
from collections import defaultdict

import pytest
from django.core.exceptions import ValidationError
from django.core.management import CommandError, call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from apps.formularios.carga import DATOS, diferencias, leer, publicar
from apps.formularios.models import Formulario, VersionFormulario
from apps.formularios.tests.factories import ESQUEMA_MINIMO, FormularioFactory

pytestmark = pytest.mark.django_db

MODELOS = {'Formulario': Formulario, 'VersionFormulario': VersionFormulario}


def _archivo(tmp_path, *, formulario=None, esquema=None, nombre='prueba_v1.json', texto=None):
    ruta = tmp_path / nombre
    if texto is None:
        texto = json.dumps(
            {
                'formulario': formulario
                or {'nombre': 'Visita', 'descripcion': '', 'genero_aplicable': 'masculino'},
                'esquema': esquema or ESQUEMA_MINIMO,
            }
        )
    ruta.write_text(texto, encoding='utf-8')
    return ruta


def _con_pregunta_nueva(esquema):
    nuevo = copy.deepcopy(esquema)
    nuevo['secciones'][0]['preguntas'].append(
        {'clave': 'pregunta_nueva', 'etiqueta': '¿Algo más?', 'tipo': 'texto'}
    )
    return nuevo


def _hombre():
    return Formulario.objects.get(activo=True, genero_aplicable='masculino')


# Leer


def test_lee_un_archivo_valido(tmp_path):
    definicion = leer(_archivo(tmp_path))
    assert definicion.nombre == 'Visita'
    assert definicion.genero_aplicable == 'masculino'
    assert definicion.esquema == ESQUEMA_MINIMO


def test_json_invalido_dice_donde(tmp_path):
    with pytest.raises(ValidationError, match='línea 1'):
        leer(_archivo(tmp_path, texto='{"formulario": '))


def test_archivo_inexistente(tmp_path):
    with pytest.raises(ValidationError, match='No existe'):
        leer(tmp_path / 'nada.json')


@pytest.mark.parametrize(
    ('datos', 'mensaje'),
    [
        ({'esquema': ESQUEMA_MINIMO}, 'debe ser'),
        ({'formulario': {'nombre': 'X', 'color': 'rojo'}, 'esquema': ESQUEMA_MINIMO}, 'solo'),
        ({'formulario': {'nombre': ' '}, 'esquema': ESQUEMA_MINIMO}, 'nombre'),
        (
            {'formulario': {'nombre': 'X', 'genero_aplicable': 'otro'}, 'esquema': ESQUEMA_MINIMO},
            'genero_aplicable',
        ),
    ],
)
def test_rechaza_la_cabecera_invalida(tmp_path, datos, mensaje):
    with pytest.raises(ValidationError, match=mensaje):
        leer(_archivo(tmp_path, texto=json.dumps(datos)))


def test_junta_los_errores_del_esquema(tmp_path):
    esquema = {
        'secciones': [
            {
                'titulo': 'A',
                'preguntas': [
                    {'clave': 'Mal', 'etiqueta': 'x', 'tipo': 'texto'},
                    {'clave': 'b', 'etiqueta': 'y', 'tipo': 'color'},
                ],
            }
        ]
    }
    with pytest.raises(ValidationError) as error:
        leer(_archivo(tmp_path, esquema=esquema))
    assert len(error.value.messages) == 2


# Publicar


def test_publica_una_version_nueva_y_despublica_la_anterior(tmp_path):
    anterior = _hombre().versiones.get(publicada=True)
    esquema = _con_pregunta_nueva(anterior.esquema)
    formulario = {'nombre': 'Visita (hombre)', 'genero_aplicable': 'masculino'}
    version, nueva = publicar(
        leer(_archivo(tmp_path, formulario=formulario, esquema=esquema)), **MODELOS
    )
    assert nueva
    assert version.numero_version == anterior.numero_version + 1
    assert version.publicada and version.esquema == esquema
    anterior.refresh_from_db()
    assert not anterior.publicada
    # Actualiza el mismo formulario aunque cambie el nombre: hay uno por género.
    assert version.formulario_id == anterior.formulario_id
    assert _hombre().nombre == 'Visita (hombre)'


def test_publicar_lo_mismo_no_crea_otra_version(tmp_path):
    definicion = leer(DATOS / 'hombre_v1.json')
    antes = VersionFormulario.objects.count()
    version, nueva = publicar(definicion, **MODELOS)
    assert not nueva
    assert version == _hombre().versiones.get(publicada=True)
    assert VersionFormulario.objects.count() == antes


def test_crea_el_formulario_si_su_genero_no_tiene(tmp_path):
    formulario = {'nombre': 'General', 'genero_aplicable': ''}
    version, nueva = publicar(leer(_archivo(tmp_path, formulario=formulario)), **MODELOS)
    assert nueva and version.numero_version == 1
    assert version.formulario.genero_aplicable == ''


def test_dos_activos_del_mismo_genero_no_se_adivina(tmp_path):
    FormularioFactory(genero_aplicable='masculino')
    with pytest.raises(ValidationError, match='mismo género'):
        publicar(leer(_archivo(tmp_path)), **MODELOS)


def test_funciona_con_los_modelos_de_una_migracion(tmp_path):
    """Las migraciones de datos lo llaman con apps.get_model(...)."""
    historicos = MigrationExecutor(connection).loader.project_state().apps
    esquema = _con_pregunta_nueva(_hombre().versiones.get(publicada=True).esquema)
    version, nueva = publicar(
        leer(_archivo(tmp_path, esquema=esquema)),
        Formulario=historicos.get_model('formularios', 'Formulario'),
        VersionFormulario=historicos.get_model('formularios', 'VersionFormulario'),
    )
    assert nueva
    assert _hombre().versiones.get(publicada=True).pk == version.pk


# Archivos del repo


def test_lo_publicado_coincide_con_el_ultimo_archivo_de_cada_genero():
    """Las migraciones y los archivos de datos/ no se desfasan."""
    ultimos = defaultdict(lambda: (0, None))
    for ruta in DATOS.glob('*.json'):
        numero = int(re.search(r'_v(\d+)\.json$', ruta.name).group(1))
        definicion = leer(ruta)
        if numero > ultimos[definicion.genero_aplicable][0]:
            ultimos[definicion.genero_aplicable] = (numero, definicion)
    assert ultimos
    for genero, (numero, definicion) in ultimos.items():
        publicada = VersionFormulario.objects.get(
            publicada=True, formulario__activo=True, formulario__genero_aplicable=genero
        )
        assert publicada.esquema == definicion.esquema, genero
        assert publicada.numero_version == numero, genero


# Diferencias


def test_diferencias_por_clave():
    nuevo = _con_pregunta_nueva(ESQUEMA_MINIMO)
    preguntas = nuevo['secciones'][0]['preguntas']
    preguntas[0]['etiqueta'] = '¿Viene en ayunas?'
    del preguntas[2]  # notas
    cambios = diferencias(ESQUEMA_MINIMO, nuevo)
    assert cambios.agregadas == ['pregunta_nueva']
    assert cambios.quitadas == ['notas']
    assert cambios.cambiadas == ['ayuno']
    assert not diferencias(ESQUEMA_MINIMO, ESQUEMA_MINIMO).hay


# Comando revisar_formulario


def test_revisar_sin_cambios(capsys):
    call_command('revisar_formulario', str(DATOS / 'hombre_v1.json'))
    salida = capsys.readouterr().out
    assert 'válido' in salida
    assert 'Sin cambios' in salida


def test_revisar_muestra_lo_que_cambia_y_no_escribe(tmp_path, capsys):
    esquema = _con_pregunta_nueva(_hombre().versiones.get(publicada=True).esquema)
    antes = VersionFormulario.objects.count()
    call_command('revisar_formulario', str(_archivo(tmp_path, esquema=esquema)))
    assert '+ Agregadas: pregunta_nueva' in capsys.readouterr().out
    assert VersionFormulario.objects.count() == antes


def test_revisar_un_archivo_con_errores(tmp_path):
    with pytest.raises(CommandError, match='problemas'):
        call_command('revisar_formulario', str(_archivo(tmp_path, texto='[]')))


def test_vista_previa_en_un_solo_archivo(tmp_path):
    destino = tmp_path / 'vista.html'
    call_command('revisar_formulario', str(DATOS / 'mujer_v1.json'), '--html', str(destino))
    html = destino.read_text(encoding='utf-8')
    assert 'Vista previa' in html
    assert '¿Está embarazada o podría estarlo?' in html
    # Sin archivos externos: se abre igual en cualquier computadora.
    assert '<style>' in html
    assert 'rel="stylesheet"' not in html
    assert 'htmx' not in html
