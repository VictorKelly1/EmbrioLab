"""
Texto de cada tipo de notificación. PROVISIONAL (CONTEXTO.md §8) hasta que el cliente
revise la redacción. Tono «usted». Nunca llevan más datos del paciente que su nombre.
"""

from django.utils import formats, timezone

from apps.documentos.pdf import nombre_archivo, nombre_cotizacion
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
    texto = f'Hola, {cita.nombre_de_pila}:\n\nLe recordamos su cita en EmbrioLab {_cuando(cita)}.'
    if link:
        texto += (
            '\n\nAntes de su visita, por favor llene el formulario de la cita en este link '
            f'(sirve una sola vez y vence el {_vigencia(cita)}):\n{link}'
        )
    texto += '\n\nSi no puede asistir, comuníquese con nosotros para reprogramarla.'
    return Mensaje(destinatario, 'Recordatorio de su cita en EmbrioLab', texto + FIRMA)


def link_formulario(destinatario: str, cita, link: str) -> Mensaje:
    texto = (
        f'Hola, {cita.nombre_de_pila}:\n\nPor favor llene el formulario de su visita a EmbrioLab '
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


def resultados_doctor(destinatario: str, estudios, pdf: bytes) -> Mensaje:
    """Al doctor que firmó la orden: los mismos resultados y PDF que recibe el paciente."""
    pedido = estudios[0].pedido
    paciente = pedido.cita.paciente.persona.nombre_completo
    nombres = '\n'.join(f'- {e.estudio.nombre}' for e in estudios)
    texto = (
        f'Estimado(a) {pedido.doctor.nombre}:\n\nLe enviamos los resultados de su paciente '
        f'{paciente} (pedido {pedido.numero}):\n{nombres}'
    )
    adjunto = Adjunto(nombre_archivo(estudios), pdf, 'application/pdf')
    asunto = f'Resultados de su paciente {paciente} · EmbrioLab'
    return Mensaje(destinatario, asunto, texto + FIRMA, (adjunto,))


def cotizacion(destinatario: str, cotizacion, pdf: bytes) -> Mensaje:
    saludo = f'Hola, {cotizacion.cliente}:' if cotizacion.cliente else 'Hola:'
    nombres = '\n'.join(f'- {r.nombre}: ${r.precio:,.2f}' for r in cotizacion.renglones)
    texto = (
        f'{saludo}\n\nLe compartimos la cotización que nos pidió:\n{nombres}'
        f'\n\nTotal: ${cotizacion.total:,.2f} MXN'
        '\n\nLos precios son los vigentes a la fecha y pueden cambiar. '
        'Para agendar su cita, comuníquese con nosotros.'
    )
    adjunto = Adjunto(nombre_cotizacion(cotizacion), pdf, 'application/pdf')
    return Mensaje(destinatario, 'Su cotización de EmbrioLab', texto + FIRMA, (adjunto,))
