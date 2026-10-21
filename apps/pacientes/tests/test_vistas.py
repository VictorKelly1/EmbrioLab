import pytest
from django.urls import reverse

from apps.cuentas.tests.factories import AdminFactory, QuimicoFactory, RecepcionistaFactory
from apps.pacientes.models import Doctor, Paciente
from apps.pacientes.tests.factories import DoctorFactory, PacienteFactory

pytestmark = pytest.mark.django_db

LISTA = reverse('pacientes:lista')
CREAR = reverse('pacientes:crear')

FORMULARIO = {
    'nombre': 'Ana',
    'apellido_paterno': 'López',
    'apellido_materno': 'García',
    'genero': 'femenino',
    'fecha_nacimiento': '1992-05-17',
    'curp': 'loga920517mjclrn09',
    'numero_ine': '',
    'whatsapp': '33 1234 5678',
    'telefono': '',
    'correo': 'ana@correo.mx',
    'calle': '',
    'numero': '',
    'colonia_frac': '',
    'ciudad': '',
    'estado': '',
    'pais': 'México',
    'codigo_postal': '',
}


@pytest.fixture
def recepcion(client):
    client.force_login(RecepcionistaFactory().usuario)
    return client


@pytest.fixture
def quimico(client):
    client.force_login(QuimicoFactory().usuario)
    return client


# Permisos


@pytest.mark.parametrize(
    'url',
    [
        LISTA,
        CREAR,
        reverse('pacientes:detalle', args=[1]),
        reverse('pacientes:doctores'),
        reverse('pacientes:doctor_crear'),
    ],
)
def test_sin_sesion_redirige_al_login(client, url):
    respuesta = client.get(url)
    assert respuesta.status_code == 302
    assert respuesta.url.startswith(reverse('cuentas:entrar'))


def test_admin_no_ve_pacientes(client):
    client.force_login(AdminFactory().usuario)
    assert client.get(LISTA).status_code == 403


def test_quimico_consulta_pero_no_edita(quimico):
    paciente = PacienteFactory()
    assert quimico.get(LISTA).status_code == 200
    detalle = quimico.get(reverse('pacientes:detalle', args=[paciente.pk]))
    assert detalle.status_code == 200
    assert 'Editar datos' not in detalle.text
    assert quimico.get(CREAR).status_code == 403
    assert quimico.get(reverse('pacientes:editar', args=[paciente.pk])).status_code == 403
    assert quimico.post(reverse('pacientes:baja', args=[paciente.pk])).status_code == 403
    assert quimico.get(reverse('pacientes:doctores')).status_code == 403


# Lista y búsqueda


def test_busqueda(recepcion):
    ana = PacienteFactory(persona__nombre='Ana', persona__apellido_paterno='López')
    PacienteFactory(persona__nombre='Luis', persona__apellido_paterno='Pérez')

    respuesta = recepcion.get(LISTA, {'q': 'lopez'})

    assert respuesta.status_code == 200
    assert ana.persona.nombre_completo in respuesta.text
    assert 'Pérez' not in respuesta.text


def test_busqueda_con_htmx_devuelve_solo_resultados(recepcion):
    PacienteFactory(persona__nombre='Ana')
    respuesta = recepcion.get(LISTA, {'q': 'ana'}, headers={'HX-Request': 'true'})
    assert '<table' in respuesta.text
    assert '<html' not in respuesta.text


def test_detalle_inexistente_es_404(recepcion):
    assert recepcion.get(reverse('pacientes:detalle', args=[999])).status_code == 404


# Registro y edición


def test_registrar_paciente(recepcion):
    respuesta = recepcion.post(CREAR, FORMULARIO)

    paciente = Paciente.objects.get()
    assert respuesta.status_code == 302
    assert respuesta.url == reverse('pacientes:detalle', args=[paciente.pk])
    assert paciente.persona.curp == 'LOGA920517MJCLRN09'
    assert paciente.persona.direccion is None

    detalle = recepcion.get(respuesta.url)
    assert 'Paciente registrado.' in detalle.text
    assert paciente.folio in detalle.text
    assert '3312345678' in detalle.text


def test_registrar_con_errores_muestra_el_formulario(recepcion):
    respuesta = recepcion.post(
        CREAR, {**FORMULARIO, 'curp': 'XXXX', 'whatsapp': '123', 'fecha_nacimiento': '2999-01-01'}
    )
    assert respuesta.status_code == 200
    errores = respuesta.context['form'].errors
    assert set(errores) == {'curp', 'whatsapp', 'fecha_nacimiento'}
    assert not Paciente.objects.exists()


def test_curp_repetida_viene_del_servicio(recepcion):
    recepcion.post(CREAR, FORMULARIO)
    respuesta = recepcion.post(CREAR, FORMULARIO)
    assert 'Ya hay un paciente con esta CURP' in respuesta.context['form'].errors['curp'][0]


def test_editar_paciente_y_foto(recepcion, imagen_png):
    recepcion.post(CREAR, FORMULARIO)
    paciente = Paciente.objects.get()
    url = reverse('pacientes:editar', args=[paciente.pk])

    formulario = recepcion.get(url)
    assert formulario.context['form'].initial['whatsapp'] == '3312345678'
    assert 'quitar_foto' not in formulario.context['form'].fields

    recepcion.post(url, {**FORMULARIO, 'nombre': 'Ana Sofía', 'foto': imagen_png})
    paciente.persona.refresh_from_db()
    assert paciente.persona.nombre == 'Ana Sofía'
    assert paciente.persona.foto

    foto = recepcion.get(reverse('personas:foto', args=[paciente.persona.pk]))
    assert foto.status_code == 200
    assert foto['Content-Type'] == 'image/png'
    assert foto['Cache-Control'] == 'private, no-store'

    assert 'quitar_foto' in recepcion.get(url).context['form'].fields
    recepcion.post(url, {**FORMULARIO, 'quitar_foto': 'on'})
    paciente.persona.refresh_from_db()
    assert not paciente.persona.foto


def test_foto_rechaza_archivos_que_no_son_imagen(recepcion):
    from django.core.files.uploadedfile import SimpleUploadedFile

    archivo = SimpleUploadedFile('foto.png', b'no soy imagen', 'image/png')
    respuesta = recepcion.post(CREAR, {**FORMULARIO, 'foto': archivo})
    assert 'foto' in respuesta.context['form'].errors


def test_foto_sin_sesion_no_se_entrega(client):
    paciente = PacienteFactory()
    respuesta = client.get(reverse('personas:foto', args=[paciente.persona.pk]))
    assert respuesta.status_code == 302


# Baja lógica


def test_dar_de_baja_y_reactivar(recepcion):
    paciente = PacienteFactory()
    url = reverse('pacientes:baja', args=[paciente.pk])

    assert recepcion.get(url).status_code == 405
    recepcion.post(url)
    paciente.refresh_from_db()
    assert paciente.estado_actividad is False
    assert paciente.persona.nombre_completo not in recepcion.get(LISTA).text

    recepcion.post(url, {'accion': 'reactivar'})
    paciente.refresh_from_db()
    assert paciente.estado_actividad is True


# Doctores


def test_registrar_y_editar_doctor(recepcion):
    respuesta = recepcion.post(
        reverse('pacientes:doctor_crear'), {'nombre': 'Dr. Juan Pérez', 'contacto': ''}
    )
    assert respuesta.status_code == 302
    doctor = Doctor.objects.get()

    recepcion.post(
        reverse('pacientes:doctor_editar', args=[doctor.pk]),
        {'nombre': 'Dr. Juan Pérez Ruiz', 'contacto': '3312345678'},
    )
    doctor.refresh_from_db()
    assert doctor.nombre == 'Dr. Juan Pérez Ruiz'


def test_lista_de_doctores(recepcion):
    DoctorFactory(nombre='Dra. Laura Gómez')
    assert 'Dra. Laura Gómez' in recepcion.get(reverse('pacientes:doctores')).text
