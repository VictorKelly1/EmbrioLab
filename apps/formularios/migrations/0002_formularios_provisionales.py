"""
Los 2 formularios de la Fase 1 (CONTEXTO.md §5): hombre y mujer.

PROVISIONAL: las preguntas son ejemplos mientras el cliente entrega las reales. Para
cambiarlas se publica una versión nueva con otra migración de datos (no se edita esta).
Solo preguntas que cambian en cada visita; nunca datos de identidad.
"""

from django.db import migrations
from django.utils import timezone

SALUD = {
    'titulo': 'Su salud reciente',
    'preguntas': [
        {
            'clave': 'medicamentos',
            'etiqueta': '¿Está tomando algún medicamento?',
            'tipo': 'si_no',
            'obligatoria': True,
        },
        {
            'clave': 'medicamentos_cuales',
            'etiqueta': '¿Cuáles medicamentos y desde cuándo?',
            'tipo': 'texto_largo',
            'obligatoria': True,
            'mostrar_si': {'clave': 'medicamentos', 'valor': True},
        },
        {
            'clave': 'enfermedad_reciente',
            'etiqueta': '¿Ha tenido fiebre o alguna enfermedad en los últimos 3 meses?',
            'tipo': 'si_no',
            'obligatoria': True,
        },
        {
            'clave': 'enfermedad_reciente_detalle',
            'etiqueta': 'Cuéntenos qué tuvo y cuándo',
            'tipo': 'texto_largo',
            'obligatoria': True,
            'mostrar_si': {'clave': 'enfermedad_reciente', 'valor': True},
        },
        {
            'clave': 'horas_ayuno',
            'etiqueta': '¿Cuántas horas de ayuno tiene?',
            'tipo': 'numero',
            'min': 0,
            'max': 72,
            'ayuda': 'Horas desde su último alimento. Escriba 0 si no está en ayuno.',
        },
    ],
}

HOMBRE = {
    'secciones': [
        {
            'titulo': 'Muestra de semen',
            'descripcion': 'Conteste solo si viene a un estudio de esperma.',
            'preguntas': [
                {
                    'clave': 'estudio_esperma',
                    'etiqueta': '¿Viene a un estudio de esperma?',
                    'tipo': 'si_no',
                    'obligatoria': True,
                },
                {
                    'clave': 'dias_abstinencia',
                    'etiqueta': '¿Cuántos días de abstinencia sexual tiene?',
                    'tipo': 'numero',
                    'obligatoria': True,
                    'min': 0,
                    'max': 60,
                    'mostrar_si': {'clave': 'estudio_esperma', 'valor': True},
                },
                {
                    'clave': 'muestra_completa',
                    'etiqueta': '¿Se recolectó la muestra completa?',
                    'tipo': 'opcion',
                    'opciones': ['Sí, completa', 'Se perdió una parte', 'Aún no la recolecto'],
                    'obligatoria': True,
                    'mostrar_si': {'clave': 'estudio_esperma', 'valor': True},
                },
            ],
        },
        SALUD,
        {
            'titulo': 'Hábitos',
            'preguntas': [
                {
                    'clave': 'fuma',
                    'etiqueta': '¿Fuma?',
                    'tipo': 'opcion',
                    'opciones': ['No', 'Ocasionalmente', 'Diario'],
                },
                {
                    'clave': 'alcohol_ultimos_dias',
                    'etiqueta': '¿Consumió alcohol en los últimos 3 días?',
                    'tipo': 'si_no',
                },
            ],
        },
    ]
}

MUJER = {
    'secciones': [
        {
            'titulo': 'Ciclo menstrual',
            'preguntas': [
                {
                    'clave': 'fecha_ultima_menstruacion',
                    'etiqueta': 'Fecha de inicio de su última menstruación',
                    'tipo': 'fecha',
                    'no_futura': True,
                    'ayuda': 'Si no la recuerda con exactitud, ponga la más aproximada.',
                },
                {
                    'clave': 'embarazo',
                    'etiqueta': '¿Está embarazada o podría estarlo?',
                    'tipo': 'opcion',
                    'opciones': ['No', 'Sí', 'No estoy segura'],
                    'obligatoria': True,
                },
                {
                    'clave': 'anticonceptivo',
                    'etiqueta': '¿Usa algún método anticonceptivo?',
                    'tipo': 'si_no',
                },
                {
                    'clave': 'anticonceptivo_cual',
                    'etiqueta': '¿Cuál o cuáles?',
                    'tipo': 'opciones',
                    'opciones': ['Pastillas', 'DIU', 'Inyección', 'Implante', 'Preservativo', 'Otro'],
                    'mostrar_si': {'clave': 'anticonceptivo', 'valor': True},
                },
            ],
        },
        SALUD,
    ]
}

FORMULARIOS = [
    ('Formulario de la visita — hombre', 'masculino', HOMBRE),
    ('Formulario de la visita — mujer', 'femenino', MUJER),
]


def crear(apps, schema_editor):
    Formulario = apps.get_model('formularios', 'Formulario')
    VersionFormulario = apps.get_model('formularios', 'VersionFormulario')
    for nombre, genero, esquema in FORMULARIOS:
        formulario = Formulario.objects.create(
            nombre=nombre,
            descripcion='PROVISIONAL: preguntas de ejemplo hasta que el cliente entregue las reales.',
            genero_aplicable=genero,
        )
        VersionFormulario.objects.create(
            formulario=formulario,
            numero_version=1,
            esquema=esquema,
            publicada=True,
            fecha_publicacion=timezone.now(),
        )


def borrar(apps, schema_editor):
    Formulario = apps.get_model('formularios', 'Formulario')
    nombres = [nombre for nombre, _, _ in FORMULARIOS]
    apps.get_model('formularios', 'VersionFormulario').objects.filter(
        formulario__nombre__in=nombres
    ).delete()
    Formulario.objects.filter(nombre__in=nombres).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('formularios', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(crear, borrar),
    ]
