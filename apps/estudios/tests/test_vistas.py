import pytest
from django.urls import reverse

from apps.cuentas.tests.factories import AdminFactory, QuimicoFactory, RecepcionistaFactory
from apps.estudios.models import Estudio, EstudioAlias, ValorReferencia
from apps.estudios.tests.factories import EstudioAliasFactory, ValorReferenciaFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def recepcion(client):
    client.force_login(RecepcionistaFactory().usuario)
    return client


@pytest.fixture
def quimico(client):
    client.force_login(QuimicoFactory().usuario)
    return client


@pytest.fixture
def lipidos():
    return Estudio.objects.get(clave='PLIP')


# Catálogo


def test_sin_sesion_redirige_al_login(client):
    assert client.get(reverse('estudios:lista')).status_code == 302


def test_el_admin_no_ve_el_catalogo(client):
    client.force_login(AdminFactory().usuario)
    assert client.get(reverse('estudios:lista')).status_code == 403


@pytest.mark.parametrize('rol', ['recepcion', 'quimico'])
def test_catalogo_agrupado_por_categoria(request, rol):
    respuesta = request.getfixturevalue(rol).get(reverse('estudios:lista'))
    assert respuesta.status_code == 200
    texto = respuesta.text
    assert texto.index('Sanguíneos') < texto.index('Perfil de lípidos') < texto.index('Esperma')
    assert 'Cultivo' not in texto  # categoría sin estudios


def test_busqueda_con_htmx_solo_devuelve_resultados(recepcion):
    respuesta = recepcion.get(
        reverse('estudios:lista'), {'q': 'seminograma'}, HTTP_HX_REQUEST='true'
    )
    assert 'Espermatobioscopia' in respuesta.text
    assert 'Glucosa' not in respuesta.text
    assert '<html' not in respuesta.text


def test_detalle_muestra_campos_referencias_y_alias(quimico, lipidos):
    respuesta = quimico.get(reverse('estudios:detalle', args=[lipidos.pk]))
    assert respuesta.status_code == 200
    for texto in (
        'Colesterol LDL',
        'Colesterol total − HDL',
        '≥ 50 mg/dL',
        'Mujeres',
        'perfil lipidico',
    ):
        assert texto in respuesta.text


def test_detalle_inexistente(quimico):
    assert quimico.get(reverse('estudios:detalle', args=[999_999])).status_code == 404


def test_cada_rol_ve_solo_sus_acciones(recepcion, lipidos):
    respuesta = recepcion.get(reverse('estudios:detalle', args=[lipidos.pk]))
    assert reverse('estudios:alias_crear', args=[lipidos.pk]) in respuesta.text
    assert reverse('estudios:referencia_crear', args=[lipidos.pk]) not in respuesta.text


# Alias


def test_recepcion_agrega_alias(recepcion, lipidos):
    respuesta = recepcion.post(
        reverse('estudios:alias_crear', args=[lipidos.pk]),
        {'alias': 'Perfil de Lípidos Completo', 'estudio': lipidos.pk},
    )
    assert respuesta.status_code == 302
    alias = EstudioAlias.objects.get(alias='perfil de lipidos completo')
    assert alias.estudio == lipidos
    assert alias.usuario_registro is not None


def test_alias_repetido_muestra_el_error(recepcion, lipidos):
    respuesta = recepcion.post(
        reverse('estudios:alias_crear', args=[lipidos.pk]),
        {'alias': 'Glucosa', 'estudio': lipidos.pk},
    )
    assert respuesta.status_code == 200
    assert 'ya corresponde a Glucosa en ayuno' in respuesta.text


def test_editar_y_eliminar_alias(recepcion, lipidos):
    alias = EstudioAliasFactory(estudio=lipidos, alias='lipidograma')
    recepcion.post(
        reverse('estudios:alias_editar', args=[alias.pk]),
        {'alias': 'Lipidograma ', 'estudio': lipidos.pk},
    )
    recepcion.post(reverse('estudios:alias_eliminar', args=[alias.pk]))
    assert not EstudioAlias.objects.filter(pk=alias.pk).exists()


def test_el_quimico_no_administra_alias(quimico, lipidos):
    alias = EstudioAliasFactory(estudio=lipidos)
    assert quimico.get(reverse('estudios:alias_crear', args=[lipidos.pk])).status_code == 403
    assert quimico.post(reverse('estudios:alias_eliminar', args=[alias.pk])).status_code == 403
    assert EstudioAlias.objects.filter(pk=alias.pk).exists()


# Valores de referencia


def _datos(**extra):
    return {
        'clave_campo': 'ldl',
        'genero': 'femenino',
        'edad_minima': '',
        'edad_maxima': '',
        'valor_minimo': '',
        'valor_maximo': '130',
        'texto_referencia': '',
        'unidad': '',
        'vigente_desde': '2026-10-21',
        **extra,
    }


def test_quimico_agrega_referencia(quimico, lipidos):
    respuesta = quimico.post(reverse('estudios:referencia_crear', args=[lipidos.pk]), _datos())
    assert respuesta.status_code == 302
    valor = lipidos.valores_referencia.get(clave_campo='ldl', genero='femenino')
    assert (valor.valor_maximo, valor.unidad) == (130, 'mg/dL')


def test_referencia_invalida_muestra_errores(quimico, lipidos):
    respuesta = quimico.post(
        reverse('estudios:referencia_crear', args=[lipidos.pk]),
        _datos(valor_minimo='200', valor_maximo='100'),
    )
    assert respuesta.status_code == 200
    assert 'no puede ser menor que el mínimo' in respuesta.text


def test_el_formulario_solo_ofrece_campos_del_estudio(quimico, lipidos):
    respuesta = quimico.get(reverse('estudios:referencia_crear', args=[lipidos.pk]))
    assert 'value="hdl"' in respuesta.text
    assert 'value="glucosa"' not in respuesta.text


def test_editar_referencia(quimico):
    valor = ValorReferenciaFactory()
    quimico.post(
        reverse('estudios:referencia_editar', args=[valor.pk]),
        _datos(clave_campo='glucosa', genero='', valor_minimo='60', valor_maximo='100'),
    )
    valor.refresh_from_db()
    assert (valor.valor_minimo, valor.valor_maximo) == (60, 100)


def test_desactivar_referencia(quimico):
    valor = ValorReferenciaFactory()
    quimico.post(reverse('estudios:referencia_activo', args=[valor.pk]), {'activo': '0'})
    assert not ValorReferencia.objects.get(pk=valor.pk).activo


def test_la_recepcion_no_administra_referencias(recepcion, lipidos):
    valor = ValorReferenciaFactory()
    assert recepcion.get(reverse('estudios:referencia_crear', args=[lipidos.pk])).status_code == 403
    respuesta = recepcion.post(
        reverse('estudios:referencia_activo', args=[valor.pk]), {'activo': '0'}
    )
    assert respuesta.status_code == 403
