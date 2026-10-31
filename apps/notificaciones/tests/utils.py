from apps.personas.services import guardar_contactos_principales

CORREO = 'paciente@example.com'
WHATSAPP = '5512345678'


def con_contactos(persona, *, correo=CORREO, whatsapp=WHATSAPP):
    guardar_contactos_principales(persona, {'correo': correo, 'whatsapp': whatsapp})
    return persona
