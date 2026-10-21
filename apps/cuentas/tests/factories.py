from decimal import Decimal

import factory

from apps.cuentas.models import Admin, Quimico, Recepcionista, Usuario
from apps.personas.tests.factories import PersonaFactory

PASSWORD = 'clave-de-prueba-123'


class UsuarioFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Usuario
        skip_postgeneration_save = True

    persona = factory.SubFactory(PersonaFactory)
    correo = factory.Sequence(lambda n: f'usuario{n}@embriolab.test')
    password = factory.django.Password(PASSWORD)


class _RolFactory(factory.django.DjangoModelFactory):
    usuario = factory.SubFactory(UsuarioFactory)
    sueldo = Decimal('10000.00')


class AdminFactory(_RolFactory):
    class Meta:
        model = Admin


class RecepcionistaFactory(_RolFactory):
    class Meta:
        model = Recepcionista


class QuimicoFactory(_RolFactory):
    class Meta:
        model = Quimico

    cedula_profesional = factory.Sequence(lambda n: f'{n:08d}')
