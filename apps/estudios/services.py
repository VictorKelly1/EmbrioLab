import datetime
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.core.texto import normalizar
from apps.estudios.models import Estudio, EstudioAlias, ValorReferencia


def _alias_libre(texto: str, *, excepto: EstudioAlias | None = None) -> str:
    alias = normalizar(texto)
    if not alias:
        raise ValidationError({'alias': 'Escriba el nombre como lo pide el doctor.'})
    existente = EstudioAlias.objects.select_related('estudio').filter(alias=alias)
    if excepto:
        existente = existente.exclude(pk=excepto.pk)
    if otro := existente.first():
        raise ValidationError({'alias': f'«{alias}» ya corresponde a {otro.estudio}.'})
    return alias


@transaction.atomic
def registrar_alias(*, estudio: Estudio, alias: str, usuario=None) -> EstudioAlias:
    """Guarda el alias normalizado (sin acentos ni mayúsculas). Un alias, un solo estudio."""
    return EstudioAlias.objects.create(
        estudio=estudio, alias=_alias_libre(alias), usuario_registro=usuario
    )


@transaction.atomic
def actualizar_alias(alias: EstudioAlias, *, estudio: Estudio, texto: str) -> EstudioAlias:
    alias.alias = _alias_libre(texto, excepto=alias)
    alias.estudio = estudio
    alias.save(update_fields=['alias', 'estudio'])
    return alias


@transaction.atomic
def eliminar_alias(alias: EstudioAlias) -> None:
    alias.delete()


def _guardar_referencia(valor: ValorReferencia) -> ValorReferencia:
    definicion = valor.estudio.definicion
    campo = definicion.campo(valor.clave_campo) if definicion else None
    if campo is None:
        raise ValidationError({'clave_campo': 'Ese campo no existe en el estudio.'})
    if campo.tipo in ('texto', 'opcion') and (
        valor.valor_minimo is not None or valor.valor_maximo is not None
    ):
        raise ValidationError(
            {'texto_referencia': 'Este campo no es numérico: use solo el texto de referencia.'}
        )
    valor.texto_referencia = valor.texto_referencia.strip()
    valor.unidad = valor.unidad.strip() or campo.unidad
    valor.full_clean()
    valor.save()
    return valor


@transaction.atomic
def registrar_valor_referencia(
    *,
    estudio: Estudio,
    clave_campo: str,
    genero: str = '',
    edad_minima: int | None = None,
    edad_maxima: int | None = None,
    valor_minimo: Decimal | None = None,
    valor_maximo: Decimal | None = None,
    texto_referencia: str = '',
    unidad: str = '',
    vigente_desde: datetime.date | None = None,
    usuario=None,
) -> ValorReferencia:
    """Sin unidad, usa la del campo en la definición del estudio."""
    valor = ValorReferencia(
        estudio=estudio,
        clave_campo=clave_campo,
        genero=genero,
        edad_minima=edad_minima,
        edad_maxima=edad_maxima,
        valor_minimo=valor_minimo,
        valor_maximo=valor_maximo,
        texto_referencia=texto_referencia,
        unidad=unidad,
        usuario_registro=usuario,
    )
    if vigente_desde:
        valor.vigente_desde = vigente_desde
    return _guardar_referencia(valor)


CAMPOS_REFERENCIA = (
    'clave_campo',
    'genero',
    'edad_minima',
    'edad_maxima',
    'valor_minimo',
    'valor_maximo',
    'texto_referencia',
    'unidad',
    'vigente_desde',
)


@transaction.atomic
def actualizar_valor_referencia(valor: ValorReferencia, **datos) -> ValorReferencia:
    """
    Corrige un valor en su lugar. Los resultados ya completados no cambian: guardan su
    propia copia de la referencia. Si el valor cambió de verdad, conviene registrar uno
    nuevo con su `vigente_desde` y desactivar este, para conservar el historial.
    """
    for campo in CAMPOS_REFERENCIA:
        if campo in datos:
            setattr(valor, campo, datos[campo])
    return _guardar_referencia(valor)


@transaction.atomic
def cambiar_activo_referencia(valor: ValorReferencia, activo: bool) -> ValorReferencia:
    valor.activo = activo
    valor.save(update_fields=['activo'])
    return valor
