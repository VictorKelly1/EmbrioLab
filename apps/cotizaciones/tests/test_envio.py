from unittest import mock

import pytest
from django.core import mail
from django.core.exceptions import ValidationError

from apps.cotizaciones.cotizacion import cotizar
from apps.cotizaciones.envio import destinos_para, enviar_cotizacion
from apps.estudios.models import Estudio
from apps.notificaciones.canales import CanalCorreo, CanalWhatsApp
from apps.notificaciones.models import Notificacion
from apps.notificaciones.tests.utils import CORREO, WHATSAPP, con_contactos
from apps.pacientes.tests.factories import PacienteFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def cotizacion():
    return cotizar(Estudio.objects.filter(clave__in=['GLU', 'PLIP']), cliente='Ana López')


def test_destinos_del_paciente():
    paciente = PacienteFactory()
    con_contactos(paciente.persona)
    assert destinos_para(paciente=paciente) == {'correo': CORREO, 'whatsapp': WHATSAPP}


def test_lo_escrito_reemplaza_al_contacto_del_paciente():
    paciente = PacienteFactory()
    con_contactos(paciente.persona)
    destinos = destinos_para(paciente=paciente, correo=' otro@example.com ')
    assert destinos == {'correo': 'otro@example.com', 'whatsapp': WHATSAPP}


def test_sin_paciente_solo_lo_escrito():
    assert destinos_para(correo='a@example.com') == {'correo': 'a@example.com'}
    assert destinos_para() == {}


def test_envia_por_correo_con_el_pdf_y_no_registra_nada(cotizacion):
    fallidos = enviar_cotizacion(cotizacion, {'correo': 'ana@example.com'})
    assert fallidos == {}
    assert len(mail.outbox) == 1
    correo = mail.outbox[0]
    assert correo.to == ['ana@example.com']
    assert 'Hola, Ana López' in correo.body
    assert 'Glucosa' in correo.body and 'Total: $' in correo.body
    nombre, contenido, tipo = correo.attachments[0]
    assert nombre.startswith('cotizacion-embriolab-') and tipo == 'application/pdf'
    assert contenido.startswith(b'%PDF')
    # Decidido: la cotización no se guarda ni deja fila en Notificaciones.
    assert not Notificacion.objects.exists()


def test_envia_por_whatsapp(cotizacion, caplog):
    with caplog.at_level('INFO', logger='apps.notificaciones'):
        assert enviar_cotizacion(cotizacion, {'whatsapp': WHATSAPP}) == {}
    assert f'WhatsApp (sin integrar) a {WHATSAPP}' in caplog.text


def test_un_canal_que_falla_se_reporta_y_el_otro_sale(cotizacion):
    with mock.patch.object(CanalCorreo, 'enviar', side_effect=OSError('SMTP caído')):
        fallidos = enviar_cotizacion(
            cotizacion, {'correo': 'ana@example.com', 'whatsapp': WHATSAPP}
        )
    assert fallidos == {'correo': 'SMTP caído'}


def test_sin_destinos(cotizacion):
    with mock.patch.object(CanalWhatsApp, 'enviar') as enviar:
        with pytest.raises(ValidationError, match='escriba un correo'):
            enviar_cotizacion(cotizacion, {})
    enviar.assert_not_called()
