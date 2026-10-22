import datetime

from django.db.models import Prefetch, Q, QuerySet
from django.utils import timezone

from apps.core.texto import normalizar
from apps.estudios.models import CategoriaEstudio, Estudio, EstudioAlias, ValorReferencia


def catalogo(termino: str = '', *, incluir_inactivos: bool = False) -> list[Estudio]:
    """
    Estudios con su categoría y sus alias. Busca por clave, nombre o alias, sin
    importar acentos ni mayúsculas. El catálogo es chico (~30), así que filtra en Python.
    """
    estudios = Estudio.objects.select_related('categoria').prefetch_related(
        Prefetch('alias', queryset=EstudioAlias.objects.only('estudio', 'alias'))
    )
    if not incluir_inactivos:
        estudios = estudios.filter(activo=True)
    buscado = normalizar(termino)
    if not buscado:
        return list(estudios)
    return [
        e
        for e in estudios
        if buscado in normalizar(e.clave)
        or buscado in normalizar(e.nombre)
        or any(buscado in a.alias for a in e.alias.all())
    ]


def categorias() -> QuerySet[CategoriaEstudio]:
    return CategoriaEstudio.objects.all()


def obtener_estudio(pk: int) -> Estudio:
    return Estudio.objects.select_related('categoria').get(pk=pk)


def alias_de(estudio: Estudio) -> QuerySet[EstudioAlias]:
    return estudio.alias.select_related('usuario_registro__persona')


def referencias_de(estudio: Estudio) -> QuerySet[ValorReferencia]:
    """Todas, activas primero: para administrarlas."""
    return estudio.valores_referencia.order_by(
        '-activo', 'clave_campo', 'genero', 'edad_minima', '-vigente_desde'
    )


def referencias_para(
    estudio: Estudio, paciente, fecha: datetime.date | None = None
) -> dict[str, ValorReferencia]:
    """
    La referencia que aplica a cada campo del estudio para este paciente en `fecha`.
    Si varias aplican, gana la de su género sobre la general, la de su edad sobre la que
    no tiene edad y, al final, la más reciente.
    """
    fecha = fecha or timezone.localdate()
    persona = paciente.persona
    edad = persona.edad_en(fecha)
    candidatas = estudio.valores_referencia.filter(
        Q(genero='') | Q(genero=persona.genero),
        Q(edad_minima__isnull=True) | Q(edad_minima__lte=edad),
        Q(edad_maxima__isnull=True) | Q(edad_maxima__gte=edad),
        activo=True,
        vigente_desde__lte=fecha,
    )
    elegidas: dict[str, ValorReferencia] = {}
    for valor in candidatas:
        actual = elegidas.get(valor.clave_campo)
        if actual is None or _prioridad(valor) > _prioridad(actual):
            elegidas[valor.clave_campo] = valor
    return elegidas


def _prioridad(valor: ValorReferencia) -> tuple:
    por_edad = valor.edad_minima is not None or valor.edad_maxima is not None
    return (bool(valor.genero), por_edad, valor.vigente_desde, valor.pk)
