"""
Datos de ejemplo para desarrollo y demos (`manage.py cargar_demo`). NUNCA en producción.

`borrar_datos` deja solo a los usuarios (con sus personas), el catálogo y los formularios
que cargan las migraciones. `cargar_datos` crea un escenario con todos los estados del flujo
usando los servicios, como lo haría el personal; para lo que pasó «antes» simula la hora
con `_a_las` y así las fechas (pedido, toma, completado) quedan coherentes.

Todo es inventado: nombres, CURP, correos (@example.com) y teléfonos.
"""

import datetime
from contextlib import contextmanager
from decimal import Decimal
from unittest import mock

from django.db import connection, models
from django.utils import timezone

from apps.citas.models import Cita
from apps.citas.services import (
    SinRegistro,
    agendar_cita,
    marcar_atendida,
    marcar_no_atendida,
    registrar_espontanea,
)
from apps.cuentas.models import Quimico, Recepcionista, Usuario
from apps.estudios.models import Estudio, EstudioAlias, ValorReferencia
from apps.formularios.constructor import construir_formulario
from apps.formularios.models import FormularioLlenado
from apps.formularios.selectors import version_para
from apps.formularios.services import guardar_respuestas
from apps.notificaciones.models import Notificacion
from apps.pacientes.models import SECUENCIA_NUMERO, Doctor, Paciente
from apps.pacientes.services import crear_doctor, registrar_paciente
from apps.pedidos.models import ConsecutivoPedido, EstadoPago, EstudioPedido, Pedido
from apps.pedidos.services import (
    Linea,
    agregar_observacion,
    cambiar_estado_pago,
    completar_estudio,
    crear_pedido,
    enviar_resultados,
    guardar_borrador,
    tomar_paciente,
)
from apps.personas.models import Direccion, Persona


def borrar_datos() -> dict[str, int]:
    """Borra todo lo operativo. Devuelve cuántas filas se borraron por tipo."""
    from django_tasks_db.models import DBTaskResult

    personas_de_usuarios = Usuario.objects.values('persona_id')
    personas = Persona.objects.exclude(pk__in=personas_de_usuarios)
    for persona in personas.exclude(foto=''):
        persona.foto.delete(save=False)

    borrados = {}
    for nombre, consulta in [
        ('notificaciones', Notificacion.objects.all()),
        ('formularios llenados', FormularioLlenado.objects.all()),
        ('estudios de pedido', EstudioPedido.objects.all()),
        ('pedidos', Pedido.objects.all()),
        ('consecutivos de pedido', ConsecutivoPedido.objects.all()),
        ('citas', Cita.objects.all()),
        ('pacientes', Paciente.objects.all()),
        ('doctores', Doctor.objects.all()),
        ('personas', personas),
        # Las que agregó el personal; las de las migraciones (sin usuario) se quedan.
        ('alias', EstudioAlias.objects.filter(usuario_registro__isnull=False)),
        ('valores de referencia', ValorReferencia.objects.filter(usuario_registro__isnull=False)),
        ('tareas', DBTaskResult.objects.all()),
    ]:
        # Pacientes y doctores tienen borrado lógico y bloquean el borrado físico; aquí, y
        # solo aquí (datos de desarrollo), se usa el delete base de QuerySet a propósito.
        borrados[nombre] = models.QuerySet.delete(consulta)[0]
    en_uso = Persona.objects.filter(direccion__isnull=False).values('direccion_id')
    borrados['direcciones'] = Direccion.objects.exclude(pk__in=en_uso).delete()[0]
    with connection.cursor() as cursor:
        cursor.execute('SELECT setval(%s, 1, false)', [SECUENCIA_NUMERO])
    return borrados


@contextmanager
def _a_las(momento: datetime.datetime):
    """Hace como si fuera `momento`: los servicios y los auto_now guardan esa hora."""
    with mock.patch('django.utils.timezone.now', return_value=momento):
        yield


def _dia(dias: int, hora: int, minuto: int = 0) -> datetime.datetime:
    """Un día hábil (lunes a sábado) a `dias` de hoy, a la hora local indicada."""
    fecha = timezone.localdate() + datetime.timedelta(days=dias)
    if fecha.weekday() == 6:  # domingo: se recorre al día hábil más cercano en esa dirección
        fecha += datetime.timedelta(days=-1 if dias < 0 else 1)
    return timezone.make_aware(datetime.datetime.combine(fecha, datetime.time(hora, minuto)))


def _antes(momento: datetime.datetime, **delta) -> datetime.datetime:
    return momento - datetime.timedelta(**delta)


def _despues(momento: datetime.datetime, **delta) -> datetime.datetime:
    return momento + datetime.timedelta(**delta)


PACIENTES = [
    # nombre, paterno, materno, género, nacimiento, CURP, correo, WhatsApp
    (
        'Mariana',
        'Torres',
        'Gutiérrez',
        'femenino',
        '1991-03-12',
        'TOGM910312MDFRTR05',
        'mariana.torres@example.com',
        '5550000101',
    ),
    (
        'José Luis',
        'Hernández',
        'Ramírez',
        'masculino',
        '1988-07-24',
        'HERJ880724HDFRMS02',
        '',
        '5550000102',
    ),
    (
        'Sofía',
        'Castillo',
        'Mendoza',
        'femenino',
        '1995-11-02',
        'CAMS951102MJCSNF08',
        'sofia.castillo@example.com',
        '',
    ),
    (
        'Daniel',
        'Rojas',
        '',
        'masculino',
        '1983-01-30',
        'ROXD830130HNLJXN04',
        'daniel.rojas@example.com',
        '5550000104',
    ),
    (
        'Fernanda',
        'Aguilar',
        'Núñez',
        'femenino',
        '1979-09-18',
        'AUNF790918MPLGXR01',
        '',
        '5550000105',
    ),
    (
        'Ricardo',
        'Salinas',
        'Pérez',
        'masculino',
        '1992-05-06',
        'SAPR920506HQTLRC09',
        'ricardo.salinas@example.com',
        '',
    ),
]

DOCTORES = [
    ('Dr. Alejandro Medina', 'dr.medina@example.com', '5550000201', 'Clínica de Fertilidad Norte'),
    ('Dra. Patricia Vega', 'dra.vega@example.com', '', 'Ginecología, consultorio 12'),
    ('Dr. Jorge Ortiz', '', '5550000203', ''),
]

RESPUESTAS = {
    'masculino': {
        'estudio_esperma': 'si',
        'dias_abstinencia': '3',
        'muestra_completa': 'Sí, completa',
        'medicamentos': 'no',
        'enfermedad_reciente': 'no',
        'horas_ayuno': '10',
        'fuma': 'No',
        'alcohol_ultimos_dias': 'no',
    },
    'femenino': {
        'medicamentos': 'no',
        'enfermedad_reciente': 'no',
        'horas_ayuno': '12',
        'embarazo': 'No',
        'anticonceptivo': 'no',
    },
}


def _usuarios():
    recepcionista = Recepcionista.objects.filter(
        estado_actividad=True, usuario__is_active=True
    ).first()
    quimicos = list(
        Quimico.objects.filter(estado_actividad=True, usuario__is_active=True).order_by('pk')[:2]
    )
    if recepcionista is None or not quimicos:
        raise ValueError('Hace falta al menos una recepcionista y un químico activos.')
    return recepcionista, quimicos[0], quimicos[-1]


def _paciente(datos) -> Paciente:
    nombre, paterno, materno, genero, nacimiento, curp, correo, whatsapp = datos
    return registrar_paciente(
        datos_persona={
            'nombre': nombre,
            'apellido_paterno': paterno,
            'apellido_materno': materno,
            'genero': genero,
            'fecha_nacimiento': datetime.date.fromisoformat(nacimiento),
            'curp': curp,
            'numero_ine': '',
        },
        contactos={'correo': correo, 'whatsapp': whatsapp, 'telefono': ''},
    )


def _llenar_formulario(cita: Cita) -> bool:
    """El paciente responde el formulario de su visita. Si el esquema cambió, se omite."""
    version = version_para(cita.genero_paciente)
    if version is None:
        return False
    form = construir_formulario(version.esquema)(data=RESPUESTAS[cita.genero_paciente])
    if not form.is_valid():
        return False
    guardar_respuestas(cita, version, form.respuestas())
    return True


def _agendada(recepcionista, cuando, *, dias_antes=3, **datos) -> Cita:
    with _a_las(_antes(cuando, days=dias_antes)):
        return agendar_cita(recepcionista=recepcionista, fecha_hora=cuando, **datos)


def cargar_datos() -> dict[str, int]:
    recepcionista, quimico, quimico2 = _usuarios()
    usuario_r = recepcionista.usuario
    estudios = {e.clave: e for e in Estudio.objects.filter(activo=True)}
    glu, plip, esp = estudios['GLU'], estudios['PLIP'], estudios['ESP']

    medina, vega, ortiz = (
        crear_doctor(nombre=n, correo=c, whatsapp=w, contacto=o) for n, c, w, o in DOCTORES
    )
    mariana, jose, sofia, daniel, fernanda, ricardo = (_paciente(p) for p in PACIENTES)
    formularios = 0

    # 1. José Luis: hace una semana. Todo completado y enviado (pedido completado).
    cuando = _dia(-7, 10)
    cita = _agendada(recepcionista, cuando, paciente=jose, asunto='Espermatobioscopia')
    with _a_las(_antes(cuando, hours=12)):
        formularios += _llenar_formulario(cita)
    with _a_las(cuando):
        marcar_atendida(cita)
        pedido = crear_pedido(
            cita=cita,
            recepcionista=recepcionista,
            doctor=medina,
            lineas=[Linea(esp, 'espermograma'), Linea(glu, 'glucosa en ayunas')],
        )
        for estudio in pedido.estudios.all():
            cambiar_estado_pago(estudio, EstadoPago.PAGADO)
    with _a_las(_despues(cuando, hours=1)):
        tomar_paciente(jose, quimico=quimico)
    with _a_las(_despues(cuando, days=1)):
        e_esp, e_glu = pedido.estudios.order_by('id')
        completar_estudio(
            e_esp,
            {
                'volumen': Decimal('2.8'),
                'concentracion': Decimal(45),
                'movilidad_progresiva': Decimal(42),
                'movilidad_no_progresiva': Decimal(18),
                'inmoviles': Decimal(40),
                'aspecto': 'Normal',
            },
            quimico=quimico,
        )
        completar_estudio(e_glu, {'glucosa': Decimal(92)}, quimico=quimico)
    with _a_las(_despues(cuando, days=1, hours=2)):
        enviar_resultados(pedido.estudios.all(), usuario=quimico.usuario, al_doctor=True)

    # 2. Mariana: hace 3 días. En proceso con Laura: glucosa completada (se puede corregir,
    #    no se ha enviado) y perfil de lípidos en borrador. Pidió todo junto.
    cuando = _dia(-3, 9)
    cita = _agendada(recepcionista, cuando, paciente=mariana, asunto='Química sanguínea')
    with _a_las(_antes(cuando, hours=20)):
        formularios += _llenar_formulario(cita)
    with _a_las(cuando):
        marcar_atendida(cita)
        pedido = crear_pedido(
            cita=cita,
            recepcionista=recepcionista,
            doctor=vega,
            lineas=[Linea(plip, 'perfil lipidico'), Linea(glu, 'glucosa')],
        )
        agregar_observacion(
            pedido, 'Enviar los resultados cuando estén todos, no por separado.', usuario=usuario_r
        )
        cambiar_estado_pago(pedido.estudios.get(estudio=glu), EstadoPago.PAGADO)
        cambiar_estado_pago(pedido.estudios.get(estudio=plip), EstadoPago.ABONADO)
    with _a_las(_despues(cuando, hours=2)):
        tomar_paciente(mariana, quimico=quimico2)
    with _a_las(_despues(cuando, days=1)):
        completar_estudio(
            pedido.estudios.get(estudio=glu), {'glucosa': Decimal(104)}, quimico=quimico2
        )
        guardar_borrador(
            pedido.estudios.get(estudio=plip),
            {'colesterol_total': Decimal(212), 'hdl': Decimal(48)},
            quimico=quimico2,
        )

    # 3. Daniel: llegó sin cita hace 2 días y volvió ayer con otra orden. Nadie lo ha tomado:
    #    en la cola aparece una vez, con sus dos pedidos.
    cuando = _dia(-2, 12)
    with _a_las(cuando):
        cita = registrar_espontanea(
            recepcionista=recepcionista, paciente=daniel, fecha_hora=cuando, asunto='Glucosa'
        )
        pedido = crear_pedido(
            cita=cita, recepcionista=recepcionista, lineas=[Linea(glu, 'glicemia')]
        )
        agregar_observacion(
            pedido, 'Mandar cada resultado conforme vaya saliendo.', usuario=usuario_r
        )
    cuando = _dia(-1, 17)
    with _a_las(cuando):
        cita = registrar_espontanea(recepcionista=recepcionista, paciente=daniel, fecha_hora=cuando)
        crear_pedido(
            cita=cita, recepcionista=recepcionista, doctor=ortiz, lineas=[Linea(esp, 'seminograma')]
        )

    # 4. Fernanda: ayer, en la cola. Su doctor no está registrado.
    cuando = _dia(-1, 16)
    cita = _agendada(recepcionista, cuando, paciente=fernanda, dias_antes=2)
    with _a_las(cuando):
        marcar_atendida(cita)
        crear_pedido(
            cita=cita,
            recepcionista=recepcionista,
            lineas=[Linea(plip, 'colesterol y trigliceridos'), Linea(glu, 'glucosa')],
        )

    # 5. No llegaron: Sofía (registrada) y Gabriela (agendó sin registro; no se guardó paciente).
    cita = _agendada(recepcionista, _dia(-1, 11), paciente=sofia, dias_antes=4)
    marcar_no_atendida(cita)
    cita = _agendada(
        recepcionista,
        _dia(-1, 13),
        dias_antes=2,
        sin_registro=SinRegistro('Gabriela', 'Ríos', 'femenino', '5550000301'),
        asunto='Perfil de lípidos',
    )
    marcar_no_atendida(cita)

    # 6. Próximas: un paciente registrado y varias sin registro.
    agendar_cita(
        recepcionista=recepcionista, paciente=ricardo, fecha_hora=_dia(1, 10), asunto='Glucosa'
    )
    agendar_cita(
        recepcionista=recepcionista,
        fecha_hora=_dia(1, 10, 30),
        sin_registro=SinRegistro('Valeria', 'Campos', 'femenino', '5550000302'),
        asunto='Química sanguínea',
    )
    agendar_cita(
        recepcionista=recepcionista,
        fecha_hora=_dia(2, 9, 30),
        sin_registro=SinRegistro('Arturo', 'Mejía', 'masculino', '', 'arturo.mejia@example.com'),
        asunto='Espermatobioscopia',
    )
    agendar_cita(
        recepcionista=recepcionista, paciente=mariana, fecha_hora=_dia(3, 12), asunto='Control'
    )
    agendar_cita(
        recepcionista=recepcionista,
        fecha_hora=_dia(4, 8, 30),
        sin_registro=SinRegistro('Héctor', 'Lara', 'masculino', '5550000303'),
    )

    return {
        'doctores': Doctor.objects.count(),
        'pacientes': Paciente.objects.count(),
        'citas': Cita.objects.count(),
        'citas sin registro': Cita.objects.filter(paciente__isnull=True).count(),
        'pedidos': Pedido.objects.count(),
        'estudios': EstudioPedido.objects.count(),
        'formularios llenados': formularios,
    }
