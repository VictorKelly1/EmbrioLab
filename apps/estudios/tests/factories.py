import factory

from apps.estudios.models import CategoriaEstudio, Estudio, EstudioAlias, ValorReferencia


class CategoriaEstudioFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = CategoriaEstudio
        django_get_or_create = ('nombre',)

    nombre = 'Sanguíneos'


class EstudioFactory(factory.django.DjangoModelFactory):
    """Estudio de prueba. Sin definición en código salvo que se use una clave real."""

    class Meta:
        model = Estudio
        django_get_or_create = ('clave',)

    clave = factory.Sequence(lambda n: f'PRUEBA{n}')
    nombre = factory.Sequence(lambda n: f'Estudio de prueba {n}')
    categoria = factory.SubFactory(CategoriaEstudioFactory)
    precio = 100


class EstudioAliasFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = EstudioAlias

    estudio = factory.SubFactory(EstudioFactory)
    alias = factory.Sequence(lambda n: f'alias {n}')


class ValorReferenciaFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ValorReferencia

    estudio = factory.LazyFunction(lambda: Estudio.objects.get(clave='GLU'))
    clave_campo = 'glucosa'
    valor_minimo = 70
    valor_maximo = 99
    unidad = 'mg/dL'
