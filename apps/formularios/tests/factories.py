import factory

from apps.formularios.models import Formulario, VersionFormulario

ESQUEMA_MINIMO = {
    'secciones': [
        {
            'titulo': 'Visita',
            'preguntas': [
                {
                    'clave': 'ayuno',
                    'etiqueta': '¿Viene en ayuno?',
                    'tipo': 'si_no',
                    'obligatoria': True,
                },
                {
                    'clave': 'horas',
                    'etiqueta': '¿Cuántas horas?',
                    'tipo': 'numero',
                    'obligatoria': True,
                    'min': 0,
                    'max': 72,
                    'mostrar_si': {'clave': 'ayuno', 'valor': True},
                },
                {'clave': 'notas', 'etiqueta': 'Notas', 'tipo': 'texto_largo'},
            ],
        }
    ]
}


class FormularioFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Formulario

    nombre = factory.Sequence(lambda n: f'Formulario {n}')
    genero_aplicable = ''


class VersionFormularioFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = VersionFormulario

    formulario = factory.SubFactory(FormularioFactory)
    numero_version = 1
    esquema = factory.LazyFunction(lambda: ESQUEMA_MINIMO)
    publicada = True
