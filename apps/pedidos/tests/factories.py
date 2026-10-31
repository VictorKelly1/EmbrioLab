from decimal import Decimal

import factory

from apps.citas.models import EstadoCita
from apps.citas.tests.factories import CitaFactory
from apps.cuentas.tests.factories import RecepcionistaFactory
from apps.estudios.models import Estudio
from apps.pedidos.models import EstudioPedido, Pedido


class PedidoFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Pedido

    cita = factory.SubFactory(CitaFactory, estado=EstadoCita.ATENDIDA)
    recepcionista = factory.SubFactory(RecepcionistaFactory)
    numero = factory.Sequence(lambda n: f'PRUEBA-{n:04d}')


class EstudioPedidoFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = EstudioPedido

    pedido = factory.SubFactory(PedidoFactory)
    estudio = factory.LazyFunction(lambda: Estudio.objects.get(clave='GLU'))
    nombre_solicitado = 'glucosa'
    precio = factory.LazyAttribute(lambda o: o.estudio.precio)
    version_estudio = 1


def estudio_completado(clave='GLU', valores=None, **extra) -> EstudioPedido:
    """Un estudio asignado y completado por un químico, como lo deja la semana 7."""
    from apps.cuentas.tests.factories import QuimicoFactory
    from apps.pedidos.services import asignar_quimicos, completar_estudio

    estudio_pedido = EstudioPedidoFactory(estudio=Estudio.objects.get(clave=clave), **extra)
    quimico = QuimicoFactory()
    asignar_quimicos(estudio_pedido, [quimico], usuario=RecepcionistaFactory().usuario)
    completar_estudio(estudio_pedido, valores or {'glucosa': Decimal(120)}, quimico=quimico)
    estudio_pedido.refresh_from_db()
    return estudio_pedido
