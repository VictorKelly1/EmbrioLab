import datetime

import factory

from apps.personas.models import Genero, Persona


def _curp(n):
    letras = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    sufijo = letras[n // 26 % 26] + letras[n % 26]
    return f'PEGA900101H{sufijo}LRA0{n % 10}'


class PersonaFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Persona

    nombre = factory.Faker('first_name', locale='es_MX')
    apellido_paterno = factory.Faker('last_name', locale='es_MX')
    apellido_materno = factory.Faker('last_name', locale='es_MX')
    genero = Genero.MASCULINO
    fecha_nacimiento = datetime.date(1990, 1, 1)
    curp = factory.Sequence(_curp)
