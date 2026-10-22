from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.cuentas.tests.factories import QuimicoFactory
from apps.estudios.models import Estudio, EstudioAlias
from apps.estudios.services import (
    actualizar_alias,
    actualizar_valor_referencia,
    cambiar_activo_referencia,
    eliminar_alias,
    registrar_alias,
    registrar_valor_referencia,
)
from apps.estudios.tests.factories import EstudioAliasFactory, ValorReferenciaFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def glucosa():
    return Estudio.objects.get(clave='GLU')


@pytest.fixture
def lipidos():
    return Estudio.objects.get(clave='PLIP')


# Alias


def test_registrar_alias_lo_normaliza(glucosa):
    usuario = QuimicoFactory().usuario
    alias = registrar_alias(estudio=glucosa, alias='  Glucosa  SÉRICA ', usuario=usuario)
    assert alias.alias == 'glucosa serica'
    assert alias.usuario_registro == usuario


def test_alias_repetido_dice_a_que_estudio_corresponde(lipidos):
    with pytest.raises(ValidationError) as error:
        registrar_alias(estudio=lipidos, alias='GLUCOSA')
    assert 'ya corresponde a Glucosa en ayuno' in error.value.message_dict['alias'][0]


def test_alias_vacio(glucosa):
    with pytest.raises(ValidationError):
        registrar_alias(estudio=glucosa, alias='  ')


def test_actualizar_alias_puede_cambiar_de_estudio(glucosa, lipidos):
    alias = registrar_alias(estudio=glucosa, alias='quimica basica')
    actualizar_alias(alias, estudio=lipidos, texto='Química básica')
    alias.refresh_from_db()
    assert (alias.alias, alias.estudio) == ('quimica basica', lipidos)


def test_actualizar_alias_a_uno_existente(glucosa):
    alias = registrar_alias(estudio=glucosa, alias='azucar')
    with pytest.raises(ValidationError):
        actualizar_alias(alias, estudio=glucosa, texto='glicemia')


def test_eliminar_alias():
    alias = EstudioAliasFactory()
    eliminar_alias(alias)
    assert not EstudioAlias.objects.filter(pk=alias.pk).exists()


# Valores de referencia


def test_registrar_referencia_usa_la_unidad_del_campo(lipidos):
    valor = registrar_valor_referencia(
        estudio=lipidos, clave_campo='ldl', genero='femenino', valor_maximo=Decimal(130)
    )
    assert valor.unidad == 'mg/dL'
    assert valor.vigente_desde == timezone.localdate()


def test_referencia_de_un_campo_que_no_existe(glucosa):
    with pytest.raises(ValidationError) as error:
        registrar_valor_referencia(estudio=glucosa, clave_campo='hdl', valor_minimo=40)
    assert 'clave_campo' in error.value.message_dict


def test_referencia_numerica_en_campo_de_opcion():
    esperma = Estudio.objects.get(clave='ESP')
    with pytest.raises(ValidationError):
        registrar_valor_referencia(estudio=esperma, clave_campo='aspecto', valor_minimo=1)
    valor = registrar_valor_referencia(
        estudio=esperma, clave_campo='aspecto', texto_referencia=' Normal '
    )
    assert valor.texto_referencia == 'Normal'


def test_referencia_sin_valores(glucosa):
    with pytest.raises(ValidationError) as error:
        registrar_valor_referencia(estudio=glucosa, clave_campo='glucosa')
    assert 'texto_referencia' in error.value.message_dict


def test_actualizar_referencia():
    valor = ValorReferenciaFactory()
    actualizar_valor_referencia(valor, valor_maximo=Decimal(100), edad_minima=18)
    valor.refresh_from_db()
    assert (valor.valor_maximo, valor.edad_minima) == (Decimal(100), 18)


def test_actualizar_referencia_valida_el_rango():
    valor = ValorReferenciaFactory()
    with pytest.raises(ValidationError):
        actualizar_valor_referencia(valor, valor_minimo=Decimal(200))


def test_desactivar_y_reactivar_referencia():
    valor = ValorReferenciaFactory()
    cambiar_activo_referencia(valor, False)
    valor.refresh_from_db()
    assert not valor.activo
    cambiar_activo_referencia(valor, True)
    valor.refresh_from_db()
    assert valor.activo
