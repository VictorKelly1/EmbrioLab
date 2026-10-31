"""
PDF de resultados, generado al vuelo con WeasyPrint (CONTEXTO.md §3: no se guardan PDFs).

Se arma solo con lo que quedó guardado al completar cada estudio (valores y referencia
copiada), así que el mismo estudio siempre produce el mismo contenido.
El formato es PROVISIONAL (CONTEXTO.md §8) hasta tener el del cliente.
"""

from django.contrib.staticfiles import finders
from django.core.exceptions import ValidationError
from django.template.loader import render_to_string
from django.utils import timezone
from weasyprint import HTML

from apps.pedidos.models import EstadoEstudio
from apps.pedidos.resultados import filas

FUENTE = 'fonts/figtree-latin-wght.woff2'


def _validar(estudios) -> None:
    if not estudios:
        raise ValidationError('No hay estudios para el PDF.')
    if len({e.pedido_id for e in estudios}) > 1:
        raise ValidationError('El PDF es de un solo pedido.')
    if any(e.estado != EstadoEstudio.COMPLETADO for e in estudios):
        raise ValidationError('Solo los estudios completados tienen resultados para entregar.')


def html_resultados(estudios) -> str:
    _validar(estudios)
    pedido = estudios[0].pedido
    cita = pedido.cita
    persona = cita.paciente.persona
    for estudio in estudios:
        estudio.filas = filas(estudio)
    fuente = finders.find(FUENTE)
    return render_to_string(
        'documentos/resultados.html',
        {
            'pedido': pedido,
            'cita': cita,
            'persona': persona,
            'edad': persona.edad_en(timezone.localdate(cita.fecha_hora)),
            'estudios': estudios,
            'generado': timezone.now(),
            'fuente': f'file://{fuente}' if fuente else '',
        },
    )


def pdf_resultados(estudios) -> bytes:
    """Un PDF con los estudios completados de un pedido, en el orden recibido."""
    return HTML(string=html_resultados(list(estudios))).write_pdf()


def nombre_archivo(estudios) -> str:
    """Sin datos del paciente en el nombre: puede quedar en una carpeta de descargas."""
    estudios = list(estudios)
    nombre = f'resultados-{estudios[0].pedido.numero}'
    if len(estudios) == 1:
        nombre += f'-{estudios[0].estudio.clave}'
    return f'{nombre}.pdf'.lower()
