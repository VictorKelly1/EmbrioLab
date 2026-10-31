from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse

from apps.cuentas.tests.factories import AdminFactory, QuimicoFactory, RecepcionistaFactory
from apps.documentos.pdf import html_resultados, nombre_archivo, pdf_resultados
from apps.estudios.tests.factories import ValorReferenciaFactory
from apps.pedidos.tests.factories import EstudioPedidoFactory, PedidoFactory, estudio_completado

pytestmark = pytest.mark.django_db


# Contenido


def test_el_pdf_es_un_pdf():
    assert pdf_resultados([estudio_completado()]).startswith(b'%PDF')


def test_lleva_al_paciente_los_valores_y_la_referencia_copiada():
    estudio = estudio_completado(valores={'glucosa': Decimal(120)})
    persona = estudio.pedido.cita.paciente.persona
    html = html_resultados([estudio])
    assert persona.nombre_completo in html
    assert estudio.pedido.cita.numero_folio in html
    assert 'Glucosa en ayuno' in html
    assert '120' in html
    assert '70 – 99 mg/dL' in html
    assert 'alto' in html


def test_la_referencia_es_la_que_se_copio_al_completar():
    estudio = estudio_completado(valores={'glucosa': Decimal(120)})
    ValorReferenciaFactory(valor_minimo=1, valor_maximo=500)
    estudio.refresh_from_db()
    html = html_resultados([estudio])
    assert '70 – 99 mg/dL' in html
    assert '1 – 500' not in html


def test_firma_quien_completo_con_su_cedula():
    estudio = estudio_completado()
    quimico = estudio.quimico_completo
    html = html_resultados([estudio])
    assert quimico.usuario.persona.nombre_completo in html
    assert quimico.cedula_profesional in html


def test_solo_estudios_completados():
    with pytest.raises(ValidationError, match='completados'):
        html_resultados([EstudioPedidoFactory()])


def test_un_solo_pedido():
    with pytest.raises(ValidationError, match='un solo pedido'):
        html_resultados([estudio_completado(), estudio_completado()])


def test_el_nombre_del_archivo_no_lleva_datos_del_paciente():
    estudio = estudio_completado()
    numero = estudio.pedido.numero.lower()
    assert nombre_archivo([estudio]) == f'resultados-{numero}-glu.pdf'
    assert nombre_archivo([estudio, estudio]) == f'resultados-{numero}.pdf'


# Vista


def _url(pedido, *estudios):
    url = reverse('documentos:resultados', args=[pedido.pk])
    if estudios:
        url += '?' + '&'.join(f'estudio={e.pk}' for e in estudios)
    return url


@pytest.mark.parametrize('fabrica', [RecepcionistaFactory, QuimicoFactory])
def test_recepcion_y_quimico_ven_el_pdf(client, fabrica):
    estudio = estudio_completado()
    client.force_login(fabrica().usuario)
    respuesta = client.get(_url(estudio.pedido))
    assert respuesta.status_code == 200
    assert respuesta['Content-Type'] == 'application/pdf'
    assert respuesta['Cache-Control'] == 'no-store'
    assert respuesta['Content-Disposition'].startswith('inline; filename="resultados-')
    assert respuesta.content.startswith(b'%PDF')


def test_el_admin_no_ve_resultados(client):
    estudio = estudio_completado()
    client.force_login(AdminFactory().usuario)
    assert client.get(_url(estudio.pedido)).status_code == 403


def test_sin_sesion_va_al_login(client):
    estudio = estudio_completado()
    assert client.get(_url(estudio.pedido)).status_code == 302


def test_sin_completados_es_404(client):
    pedido = PedidoFactory()
    EstudioPedidoFactory(pedido=pedido)
    client.force_login(QuimicoFactory().usuario)
    assert client.get(_url(pedido)).status_code == 404


def test_se_puede_pedir_un_solo_estudio(client):
    pedido = PedidoFactory()
    glucosa = estudio_completado(pedido=pedido)
    estudio_completado(
        'PLIP',
        {'colesterol_total': Decimal(210), 'hdl': Decimal(45), 'trigliceridos': Decimal(150)},
        pedido=pedido,
    )
    client.force_login(QuimicoFactory().usuario)
    respuesta = client.get(_url(pedido, glucosa))
    assert respuesta['Content-Disposition'].endswith('-glu.pdf"')


def test_un_estudio_de_otro_pedido_no_entra(client):
    pedido = PedidoFactory()
    EstudioPedidoFactory(pedido=pedido)
    ajeno = estudio_completado()
    client.force_login(QuimicoFactory().usuario)
    assert client.get(_url(pedido, ajeno)).status_code == 404
