"""
`Doctor.contacto` era texto libre. Si todo el texto es un correo pasa a `correo`; si es un
número de 10 a 15 dígitos (con o sin espacios, guiones o paréntesis) pasa a `whatsapp`.
Lo demás se queda en `contacto` («otros datos de contacto»).
"""

import re

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import migrations

TELEFONO = re.compile(r'^\+?[0-9]{10,15}$')


def _es_correo(texto: str) -> bool:
    try:
        validate_email(texto)
    except ValidationError:
        return False
    return True


def separar(apps, schema_editor):
    Doctor = apps.get_model('pacientes', 'Doctor')
    for doctor in Doctor.objects.exclude(contacto=''):
        texto = doctor.contacto.strip()
        numero = re.sub(r'[\s\-().]', '', texto)
        if _es_correo(texto):
            doctor.correo, doctor.contacto = texto.lower(), ''
        elif TELEFONO.match(numero):
            doctor.whatsapp, doctor.contacto = numero, ''
        else:
            continue
        doctor.save(update_fields=['correo', 'whatsapp', 'contacto'])


def juntar(apps, schema_editor):
    Doctor = apps.get_model('pacientes', 'Doctor')
    for doctor in Doctor.objects.all():
        datos = [d for d in (doctor.correo, doctor.whatsapp, doctor.contacto) if d]
        doctor.contacto = ' · '.join(datos)[:200]
        doctor.save(update_fields=['contacto'])


class Migration(migrations.Migration):
    dependencies = [
        ('pacientes', '0002_doctor_correo_whatsapp'),
    ]

    operations = [
        migrations.RunPython(separar, juntar),
    ]
