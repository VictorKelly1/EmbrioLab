"""
Texto de cada tipo de notificación. PROVISIONAL (CONTEXTO.md §8) hasta que el cliente
revise la redacción. Tono «usted». Nunca llevan más datos del paciente que su nombre.
"""

from django.utils import formats, timezone

from apps.documentos.pdf import nombre_archivo
from apps.notificaciones.canales import Adjunto, Mensaje

FIRMA = '\n\nAtentamente,\nEmbrioLab'


def _cuando(cita) -> str:
    local = timezone.localtime(cita.fecha_hora)
    fecha = formats.date_format(local, r'l j \d\e F').lower()
    return f'el {fecha} a las {local:%H:%M}'


def _vigencia(cita) -> str:
    local = timezone.localtime(cita.token_expiracion)
    fecha = formats.date_format(local, r'j \d\e F').lower()
    return f'{fecha} a las {local:%H:%M}'


def recordatorio(destinatario: str, cita, link: str | None) -> Mensaje:
    persona = cita.paciente.persona
    texto = f'Hola, {persona.nombre}:\n\nLe recordamos su cita en EmbrioLab {_cuando(cita)}.'
    if link:
        texto += (
            '\n\nAntes de su visita, por favor llene el formulario de la cita en este link '
            f'(sirve una sola vez y vence el {_vigencia(cita)}):\n{link}'
        )
    texto += '\n\nSi no puede asistir, comuníquese con nosotros para reprogramarla.'
    return Mensaje(destinatario, 'Recordatorio de su cita en EmbrioLab', texto + FIRMA)


def link_formulario(destinatario: str, cita, link: str) -> Mensaje:
    persona = cita.paciente.persona
    texto = (
        f'Hola, {persona.nombre}:\n\nPor favor llene el formulario de su visita a EmbrioLab '
        f'en este link. Sirve una sola vez y vence el {_vigencia(cita)}.\n{link}'
    )
    return Mensaje(destinatario, 'Formulario de su visita a EmbrioLab', texto + FIRMA)


def resultados(destinatario: str, estudios, pdf: bytes) -> Mensaje:
    persona = estudios[0].pedido.cita.paciente.persona
    nombres = '\n'.join(f'- {e.estudio.nombre}' for e in estudios)
    texto = (
        f'Hola, {persona.nombre}:\n\nAdjuntamos los resultados de sus estudios:\n{nombres}'
        '\n\nPara interpretarlos, consulte a su médico.'
    )
    adjunto = Adjunto(nombre_archivo(estudios), pdf, 'application/pdf')
    return Mensaje(destinatario, 'Sus resultados de EmbrioLab', texto + FIRMA, (adjunto,))
