import pytest
from django.core.management import CommandError, call_command

from apps.citas.models import Cita, EstadoCita
from apps.citas.tests.factories import CitaFactory
from apps.core.demo import USUARIOS
from apps.cuentas.models import Usuario
from apps.cuentas.tests.factories import QuimicoFactory, RecepcionistaFactory
from apps.estudios.models import EstudioAlias
from apps.estudios.services import registrar_alias
from apps.formularios.models import FormularioLlenado
from apps.pacientes.models import Doctor, Paciente
from apps.pedidos.models import EstudioPedido, Pedido
from apps.pedidos.selectors import cola_por_paciente, encargado_del_paciente
from apps.pedidos.tests.factories import EstudioPedidoFactory
from apps.personas.models import Persona

pytestmark = pytest.mark.django_db


@pytest.fixture
def en_desarrollo(settings):
    settings.DEBUG = True


@pytest.fixture
def personal():
    return RecepcionistaFactory(), QuimicoFactory(), QuimicoFactory()


def test_sin_confirmar_no_borra(en_desarrollo, personal):
    EstudioPedidoFactory()
    with pytest.raises(CommandError, match='--confirmar'):
        call_command('cargar_demo')
    assert Pedido.objects.exists()


def test_nunca_sin_debug(settings, personal):
    settings.DEBUG = False
    EstudioPedidoFactory()
    with pytest.raises(CommandError, match='desarrollo'):
        call_command('cargar_demo', '--confirmar')
    assert Pedido.objects.exists()


def test_borra_todo_menos_los_usuarios_y_carga_el_ejemplo(en_desarrollo, personal):
    recepcionista, quimico, quimico2 = personal
    viejo = EstudioPedidoFactory()
    registrar_alias(estudio=viejo.estudio, alias='azucar', usuario=recepcionista.usuario)
    alias_de_migracion = EstudioAlias.objects.filter(usuario_registro__isnull=True).count()
    usuarios = set(Usuario.objects.values_list('pk', 'persona_id'))

    call_command('cargar_demo', '--confirmar')

    assert set(Usuario.objects.values_list('pk', 'persona_id')) == usuarios
    assert not Pedido.objects.filter(pk=viejo.pedido_id).exists()
    assert not Paciente.objects.filter(pk=viejo.pedido.cita.paciente_id).exists()
    assert not EstudioAlias.objects.filter(alias='azucar').exists()
    assert EstudioAlias.objects.count() == alias_de_migracion
    # Las respuestas de ejemplo siguen siendo válidas para los formularios publicados.
    generos = set(
        FormularioLlenado.objects.values_list(
            'version_formulario__formulario__genero_aplicable', flat=True
        )
    )
    assert generos == {'masculino', 'femenino'}
    # Las personas que quedan son las de los usuarios y las de los pacientes nuevos.
    assert Persona.objects.count() == len(usuarios) + Paciente.objects.count()

    assert Paciente.objects.count() == 6
    assert Paciente.objects.order_by('numero').first().numero == 1
    assert Doctor.objects.count() == 3
    assert Cita.objects.filter(paciente__isnull=True).count() == 4
    assert Cita.objects.filter(estado=EstadoCita.NO_ATENDIDA).count() == 2
    # Todos los estados del flujo.
    estados = set(EstudioPedido.objects.values_list('estado', flat=True))
    assert estados == {'pendiente', 'en_proceso', 'completado'}
    assert EstudioPedido.objects.filter(fecha_envio__isnull=False).count() == 2
    assert Pedido.objects.filter(estado='completado').count() == 1
    # Daniel espera en la cola con sus dos pedidos; Mariana la tiene Laura.
    cola = {g.paciente.persona.nombre: len(g.pedidos) for g in cola_por_paciente()}
    assert cola == {'Daniel': 2, 'Fernanda': 1}
    mariana = Paciente.objects.get(persona__nombre='Mariana')
    assert encargado_del_paciente(mariana) == quimico2


def test_se_puede_correr_dos_veces(en_desarrollo, personal):
    call_command('cargar_demo', '--confirmar')
    call_command('cargar_demo', '--confirmar')
    assert Paciente.objects.count() == 6


def test_solo_borrar(en_desarrollo, personal):
    CitaFactory()
    call_command('cargar_demo', '--confirmar', '--solo-borrar')
    assert not Cita.objects.exists()
    assert not Paciente.objects.exists()


def test_con_usuarios_desde_una_base_vacia(en_desarrollo, monkeypatch, capsys):
    monkeypatch.setenv('DEMO_PASSWORD', 'Demo-local-2026!')
    call_command('cargar_demo', '--confirmar', '--con-usuarios')
    assert 'Demo-local-2026!' in capsys.readouterr().out
    correos = set(Usuario.objects.values_list('correo', flat=True))
    assert correos == {u[0] for u in USUARIOS}
    assert Usuario.objects.get(correo='quimico@embriolab.local').check_password('Demo-local-2026!')
    assert Paciente.objects.count() == 6
    # La segunda vez no los repite ni cambia su contraseña.
    call_command('cargar_demo', '--confirmar', '--con-usuarios')
    assert 'ya existían' in capsys.readouterr().out
    assert Usuario.objects.count() == len(USUARIOS)


def test_sin_personal_avisa_sin_borrar(en_desarrollo):
    cita = CitaFactory()
    Usuario.objects.filter(recepcionista__isnull=False).update(is_active=False)
    with pytest.raises(CommandError, match='recepcionista'):
        call_command('cargar_demo', '--confirmar')
    assert Cita.objects.filter(pk=cita.pk).exists()
