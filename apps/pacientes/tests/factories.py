import factory

from apps.pacientes.models import Doctor, Paciente
from apps.personas.tests.factories import PersonaFactory


class PacienteFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Paciente

    persona = factory.SubFactory(PersonaFactory)
    # Lejos de los números que da la secuencia, para no chocar en las pruebas.
    numero = factory.Sequence(lambda n: 900_000 + n)


class DoctorFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Doctor

    nombre = factory.Faker('name', locale='es_MX')
    contacto = '3312345678'
