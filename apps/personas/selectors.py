from django.contrib.postgres.search import TrigramWordSimilarity
from django.db.models import Q, QuerySet

from apps.core.texto import normalizar
from apps.personas.models import Persona


def filtrar_por_nombre(
    queryset: QuerySet, termino: str, campo: str = 'nombre_busqueda'
) -> QuerySet:
    """
    Búsqueda tolerante a acentos, mayúsculas y errores de dedo sobre el nombre completo.

    Cada palabra del término debe aparecer en el nombre, completa, como parte de una
    palabra o parecida (trigramas). Ordena de la coincidencia más cercana a la más lejana.
    `campo` permite buscar desde otro modelo: 'persona__nombre_busqueda'.
    """
    termino = normalizar(termino)
    if not termino:
        return queryset
    for palabra in termino.split():
        queryset = queryset.filter(
            Q(**{f'{campo}__contains': palabra}) | Q(**{f'{campo}__trigram_word_similar': palabra})
        )
    return queryset.annotate(similitud=TrigramWordSimilarity(termino, campo)).order_by('-similitud')


def contactos_principales(persona: Persona) -> dict[str, str]:
    """{tipo: valor} de los contactos principales."""
    return {c.tipo: c.valor for c in persona.contactos.all() if c.principal}
