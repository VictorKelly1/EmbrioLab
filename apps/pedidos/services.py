from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.citas.models import Cita, EstadoCita
from apps.core.texto import normalizar
from apps.cuentas.models import Quimico, Recepcionista
from apps.estudios.models import Estudio, EstudioAlias
from apps.estudios.selectors import referencias_para
from apps.estudios.services import registrar_alias
from apps.notificaciones.services import notificar_resultados
from apps.pacientes.models import Doctor, Paciente
from apps.pedidos.estados import (
    TransicionInvalida,
    estado_del_pedido,
    pago_del_pedido,
    total_del_pedido,
    validar_transicion,
)
from apps.pedidos.models import (
    EstadoEstudio,
    EstadoPago,
    EstadoPedido,
    EstudioPedido,
    ObservacionPedido,
    Pedido,
)
from apps.pedidos.numero import siguiente_numero
from apps.pedidos.selectors import encargado_del_paciente, estudios_del_paciente


@dataclass(frozen=True)
class Linea:
    """Un estudio de la orden: lo que pidió el doctor y a qué estudio del catálogo corresponde."""

    estudio: Estudio
    nombre_solicitado: str = ''
    guardar_alias: bool = False


LARGO_OBSERVACION = 500


@transaction.atomic
def agregar_observacion(pedido: Pedido, texto: str, *, usuario) -> ObservacionPedido:
    """Una nota libre en el pedido. Solo se agregan; no se editan ni se borran."""
    texto = (texto or '').strip()
    if not texto:
        raise ValidationError({'texto': 'Escriba la observación.'})
    if len(texto) > LARGO_OBSERVACION:
        raise ValidationError(
            {'texto': f'La observación admite hasta {LARGO_OBSERVACION} caracteres.'}
        )
    return ObservacionPedido.objects.create(pedido=pedido, texto=texto, usuario=usuario)


@transaction.atomic
def crear_pedido(
    *,
    cita: Cita,
    recepcionista: Recepcionista,
    lineas: list[Linea],
    doctor: Doctor | None = None,
) -> Pedido:
    """PROVISIONAL (CONTEXTO.md §8): solo de citas atendidas, sin estudios repetidos."""
    cita = Cita.objects.select_for_update().get(pk=cita.pk)
    if cita.estado != EstadoCita.ATENDIDA:
        raise ValidationError('Marque la cita como atendida antes de armar su pedido.')
    if not lineas:
        raise ValidationError('Agregue al menos un estudio.')
    claves = [linea.estudio.pk for linea in lineas]
    if len(claves) != len(set(claves)):
        raise ValidationError('Hay un estudio repetido en el pedido.')
    pedido = Pedido.objects.create(
        cita=cita, recepcionista=recepcionista, doctor=doctor, numero=siguiente_numero()
    )
    for linea in lineas:
        _agregar(pedido, linea, recepcionista.usuario)
    return recalcular_pedido(pedido)


@transaction.atomic
def agregar_estudio(pedido: Pedido, linea: Linea, *, usuario) -> EstudioPedido:
    pedido = _bloquear(pedido)
    if pedido.estado == EstadoPedido.COMPLETADO:
        raise ValidationError('El pedido ya está completado.')
    if pedido.estudios.filter(estudio=linea.estudio).exists():
        raise ValidationError(f'{linea.estudio} ya está en el pedido.')
    estudio_pedido = _agregar(pedido, linea, usuario)
    recalcular_pedido(pedido)
    return estudio_pedido


@transaction.atomic
def quitar_estudio(estudio_pedido: EstudioPedido) -> None:
    """Solo antes de completarse. Un pedido no se queda sin estudios."""
    pedido = _bloquear(estudio_pedido.pedido)
    estudio_pedido = EstudioPedido.objects.select_for_update().get(pk=estudio_pedido.pk)
    if estudio_pedido.estado == EstadoEstudio.COMPLETADO:
        raise ValidationError('No se puede quitar un estudio completado.')
    if pedido.estudios.count() == 1:
        raise ValidationError('El pedido debe tener al menos un estudio.')
    estudio_pedido.delete()
    recalcular_pedido(pedido)


def _agregar(pedido: Pedido, linea: Linea, usuario) -> EstudioPedido:
    estudio = linea.estudio
    if not estudio.activo:
        raise ValidationError(f'{estudio} ya no está activo en el catálogo.')
    nombre = ' '.join(linea.nombre_solicitado.split()) or estudio.nombre
    if linea.guardar_alias:
        _guardar_alias(estudio, nombre, usuario)
    estudio_pedido = EstudioPedido(
        pedido=pedido,
        estudio=estudio,
        nombre_solicitado=nombre,
        precio=estudio.precio,
        version_estudio=estudio.version_definicion,
    )
    # Si el paciente ya tiene químico a cargo, el estudio nuevo es suyo (CONTEXTO.md §3).
    encargado = encargado_del_paciente(_bloquear_paciente(pedido.cita.paciente))
    if encargado is not None and encargado.estado_actividad and encargado.usuario.is_active:
        estudio_pedido.estado = EstadoEstudio.EN_PROCESO
        estudio_pedido.quimico_encargado = encargado
        estudio_pedido.fecha_toma = timezone.now()
    estudio_pedido.save()
    return estudio_pedido


def _guardar_alias(estudio: Estudio, nombre: str, usuario) -> None:
    """Si ya existe para ese estudio no hace nada; si es de otro estudio, avisa."""
    alias = normalizar(nombre)
    if alias == normalizar(estudio.nombre):
        return
    existente = EstudioAlias.objects.select_related('estudio').filter(alias=alias).first()
    if existente is None:
        registrar_alias(estudio=estudio, alias=nombre, usuario=usuario)
    elif existente.estudio_id != estudio.pk:
        raise ValidationError(
            f'«{nombre}» ya es alias de {existente.estudio}. '
            'Elija ese estudio o no guarde el nombre como alias.'
        )


def _validar_activo(quimico: Quimico) -> None:
    if not (quimico.estado_actividad and quimico.usuario.is_active):
        raise ValidationError(f'{quimico.usuario.persona.nombre_completo} está dado de baja.')


def tiene_captura(estudio_pedido: EstudioPedido) -> bool:
    """Si ya hay algún valor capturado (un borrador vacío no cuenta)."""
    return bool((estudio_pedido.resultados or {}).get('valores'))


def _bloquear_paciente(paciente: Paciente) -> Paciente:
    """
    Serializa lo que cambia al encargado de un paciente (tomar, soltar, pasar y los
    estudios nuevos que se le asignan solos), para que dos químicos no lo tomen a la vez.
    """
    return Paciente.objects.select_for_update().get(pk=paciente.pk)


def _a_cargo(paciente: Paciente, quimico: Quimico) -> list[EstudioPedido]:
    """Soltar o pasar: los estudios en proceso del paciente a cargo del químico, sin captura."""
    estudios = list(
        estudios_del_paciente(paciente)
        .filter(estado=EstadoEstudio.EN_PROCESO, quimico_encargado=quimico)
        .select_related('estudio')
        .select_for_update(of=('self',))
    )
    if not estudios:
        raise ValidationError('Este paciente no está a su cargo.')
    capturados = [str(e.estudio) for e in estudios if tiene_captura(e)]
    if capturados:
        raise ValidationError(
            f'Ya hay resultados capturados de {", ".join(capturados)}: '
            'el paciente ya no se puede soltar ni pasar.'
        )
    return estudios


def _recalcular_pedidos(estudios: list[EstudioPedido]) -> None:
    for pedido_id in sorted({e.pedido_id for e in estudios}):
        recalcular_pedido(Pedido(pk=pedido_id))


@transaction.atomic
def tomar_paciente(paciente: Paciente, *, quimico: Quimico) -> list[EstudioPedido]:
    """
    El químico toma de la cola a un paciente: todos sus estudios pendientes, de todos
    sus pedidos, quedan a su cargo y en proceso (CONTEXTO.md §3). Si otro químico ya
    lo tiene, avisa; el bloqueo del paciente evita que dos lo tomen a la vez.
    """
    paciente = _bloquear_paciente(paciente)
    _validar_activo(quimico)
    encargado = encargado_del_paciente(paciente)
    if encargado is not None and encargado.pk != quimico.pk:
        raise ValidationError(
            f'{encargado.usuario.persona.nombre_completo} ya tiene a este paciente a su cargo.'
        )
    estudios = list(
        estudios_del_paciente(paciente)
        .filter(
            estado=EstadoEstudio.PENDIENTE,
            quimico_encargado__isnull=True,
            pedido__cita__estado=EstadoCita.ATENDIDA,
        )
        .select_for_update(of=('self',))
    )
    if not estudios:
        raise ValidationError('Este paciente no tiene estudios en espera.')
    ahora = timezone.now()
    for estudio_pedido in estudios:
        validar_transicion(estudio_pedido.estado, EstadoEstudio.EN_PROCESO)
        estudio_pedido.estado = EstadoEstudio.EN_PROCESO
        estudio_pedido.quimico_encargado = quimico
        estudio_pedido.fecha_toma = ahora
    EstudioPedido.objects.bulk_update(estudios, ['estado', 'quimico_encargado', 'fecha_toma'])
    _recalcular_pedidos(estudios)
    return estudios


@transaction.atomic
def soltar_paciente(paciente: Paciente, *, quimico: Quimico) -> list[EstudioPedido]:
    """
    El encargado regresa al paciente a la cola: sus estudios en proceso vuelven a
    pendientes. Solo si todavía no captura nada de ninguno.
    """
    paciente = _bloquear_paciente(paciente)
    estudios = _a_cargo(paciente, quimico)
    for estudio_pedido in estudios:
        estudio_pedido.estado = EstadoEstudio.PENDIENTE
        estudio_pedido.quimico_encargado = None
        estudio_pedido.fecha_toma = None
    EstudioPedido.objects.bulk_update(estudios, ['estado', 'quimico_encargado', 'fecha_toma'])
    _recalcular_pedidos(estudios)
    return estudios


@transaction.atomic
def pasar_paciente(paciente: Paciente, nuevo: Quimico, *, quimico: Quimico) -> list[EstudioPedido]:
    """El encargado pasa al paciente a otro químico, si aún no captura nada. Siguen en proceso."""
    paciente = _bloquear_paciente(paciente)
    estudios = _a_cargo(paciente, quimico)
    if nuevo.pk == quimico.pk:
        raise ValidationError('Elija a otro químico.')
    _validar_activo(nuevo)
    ahora = timezone.now()
    for estudio_pedido in estudios:
        estudio_pedido.quimico_encargado = nuevo
        estudio_pedido.fecha_toma = ahora
    EstudioPedido.objects.bulk_update(estudios, ['quimico_encargado', 'fecha_toma'])
    return estudios


@transaction.atomic
def cambiar_estado_pago(estudio_pedido: EstudioPedido, estado_pago: str) -> EstudioPedido:
    """
    La ÚNICA forma de cambiar el pago (CONTEXTO.md §3): aquí se conectará la tabla
    Abonos en una fase posterior. El envío de resultados no depende del pago.
    """
    if estado_pago not in EstadoPago.values:
        raise ValidationError('Estado de pago no válido.')
    estudio_pedido = EstudioPedido.objects.select_for_update().get(pk=estudio_pedido.pk)
    estudio_pedido.estado_pago = estado_pago
    estudio_pedido.save(update_fields=['estado_pago'])
    recalcular_pedido(estudio_pedido.pedido)
    return estudio_pedido


@transaction.atomic
def cambiar_pago_pedido(pedido: Pedido, estado_pago: str) -> Pedido:
    """El mismo estado de pago para todos los estudios del pedido."""
    for estudio_pedido in pedido.estudios.all():
        cambiar_estado_pago(estudio_pedido, estado_pago)
    return recalcular_pedido(pedido)


def _para_capturar(estudio_pedido: EstudioPedido, quimico: Quimico):
    """
    Bloquea el estudio y revisa que se pueda capturar. PROVISIONAL (CONTEXTO.md §8):
    solo su químico encargado y solo mientras está en proceso.
    """
    estudio_pedido = (
        EstudioPedido.objects.select_for_update(of=('self',))
        .select_related('estudio', 'pedido__cita__paciente__persona')
        .get(pk=estudio_pedido.pk)
    )
    if estudio_pedido.estado != EstadoEstudio.EN_PROCESO:
        raise TransicionInvalida(
            f'El estudio está {estudio_pedido.get_estado_display().lower()}: '
            'solo se capturan resultados de un estudio en proceso.'
        )
    if estudio_pedido.quimico_encargado_id != quimico.pk:
        raise ValidationError('Este estudio no está a su cargo.')
    definicion = estudio_pedido.estudio.definicion
    if definicion is None:
        raise ValidationError('El estudio no tiene definición en el código.')
    return estudio_pedido, definicion


def _capturados(definicion, valores: dict) -> dict:
    """Solo los campos que captura el químico; los vacíos no se guardan."""
    claves = {c.clave for c in definicion.campos}
    desconocidos = valores.keys() - claves
    if desconocidos:
        raise ValidationError(f'Campos que no son del estudio: {", ".join(sorted(desconocidos))}.')
    return {c: v for c, v in valores.items() if v not in (None, '')}


@transaction.atomic
def guardar_borrador(estudio_pedido: EstudioPedido, valores: dict, *, quimico: Quimico):
    """
    PROVISIONAL. Guarda lo capturado hasta ahora, sin calcular ni validar que esté completo.
    El estudio sigue en proceso.
    """
    estudio_pedido, definicion = _para_capturar(estudio_pedido, quimico)
    estudio_pedido.resultados = {
        'version': definicion.version,
        'valores': definicion.a_json(_capturados(definicion, valores)),
    }
    estudio_pedido.version_estudio = definicion.version
    estudio_pedido.save(update_fields=['resultados', 'version_estudio'])
    return estudio_pedido


@transaction.atomic
def completar_estudio(estudio_pedido: EstudioPedido, valores: dict, *, quimico: Quimico):
    """
    Valida y calcula con la definición del estudio, copia las referencias que aplican al
    paciente (CONTEXTO.md §3) y lo marca completado. Completado ya no se corrige.

    Resultados: {'version', 'valores' (capturados y calculados), 'referencias' (por campo)}.
    PROVISIONAL: la referencia que aplica es la vigente el día de la cita, con la edad
    que tenía el paciente ese día.
    """
    estudio_pedido, definicion = _para_capturar(estudio_pedido, quimico)
    capturados = _capturados(definicion, valores)
    faltan = {
        c.clave: 'Capture este valor para completar el estudio.'
        for c in definicion.campos
        if c.clave not in capturados
    }
    if faltan:
        raise ValidationError(faltan)
    cita = estudio_pedido.pedido.cita
    resultados = definicion.resultados(capturados, cita.paciente)
    referencias = referencias_para(
        estudio_pedido.estudio, cita.paciente, timezone.localdate(cita.fecha_hora)
    )
    validar_transicion(estudio_pedido.estado, EstadoEstudio.COMPLETADO)
    estudio_pedido.resultados = {
        'version': definicion.version,
        'valores': definicion.a_json(resultados),
        'referencias': {
            clave: referencia.como_json()
            for clave, referencia in sorted(referencias.items())
            if clave in resultados
        },
    }
    estudio_pedido.version_estudio = definicion.version
    estudio_pedido.estado = EstadoEstudio.COMPLETADO
    estudio_pedido.quimico_completo = quimico
    estudio_pedido.fecha_completado = timezone.now()
    estudio_pedido.save(
        update_fields=[
            'resultados',
            'version_estudio',
            'estado',
            'quimico_completo',
            'fecha_completado',
        ]
    )
    recalcular_pedido(estudio_pedido.pedido)
    return estudio_pedido


@transaction.atomic
def enviar_resultados(estudios, *, usuario, al_doctor: bool = False) -> list[EstudioPedido]:
    """
    Envía al paciente los resultados de uno o varios estudios completados de un pedido,
    en un solo mensaje por canal con un PDF (CONTEXTO.md §3). No depende del pago.
    Con `al_doctor`, también al doctor del pedido si tiene correo o WhatsApp.

    Queda registrado quién envió y cuándo. PROVISIONAL (CONTEXTO.md §8): se puede
    reenviar un estudio ya enviado; la fecha y el usuario del primer envío no cambian.
    """
    pks = [e.pk for e in estudios]
    if not pks:
        raise ValidationError('Elija al menos un estudio para enviar.')
    estudios = list(
        EstudioPedido.objects.select_for_update(of=('self',))
        .select_related('pedido__cita__paciente__persona', 'pedido__doctor')
        .filter(pk__in=pks)
        .order_by('id')
    )
    if len({e.pedido_id for e in estudios}) != 1:
        raise ValidationError('Los estudios a enviar deben ser de un mismo pedido.')
    pendientes = [e for e in estudios if e.estado != EstadoEstudio.COMPLETADO]
    if pendientes:
        nombres = ', '.join(str(e.estudio) for e in pendientes)
        raise TransicionInvalida(f'Solo se envían estudios completados: {nombres}.')
    notificar_resultados(estudios, al_doctor=al_doctor)
    ahora = timezone.now()
    for estudio_pedido in estudios:
        if not estudio_pedido.enviado:
            estudio_pedido.usuario_envio = usuario
            estudio_pedido.fecha_envio = ahora
            estudio_pedido.save(update_fields=['usuario_envio', 'fecha_envio'])
    recalcular_pedido(estudios[0].pedido)
    return estudios


@transaction.atomic
def cambiar_doctor(pedido: Pedido, doctor: Doctor | None) -> Pedido:
    pedido = _bloquear(pedido)
    pedido.doctor = doctor
    pedido.save(update_fields=['doctor'])
    return pedido


@transaction.atomic
def recalcular_pedido(pedido: Pedido) -> Pedido:
    """
    El ÚNICO que escribe los derivados del pedido (CONTEXTO.md §5). Se llama tras
    cualquier cambio en sus estudios.
    """
    pedido = _bloquear(pedido)
    estudios = list(pedido.estudios.all())
    pedido.estado = estado_del_pedido(estudios)
    pedido.estado_pago = pago_del_pedido(estudios)
    pedido.total_pago = total_del_pedido(estudios)
    completados = estudios and all(e.estado == EstadoEstudio.COMPLETADO for e in estudios)
    enviados = estudios and all(e.enviado for e in estudios)
    pedido.fecha_completado = max(e.fecha_completado for e in estudios) if completados else None
    pedido.fecha_envio = max(e.fecha_envio for e in estudios) if enviados else None
    pedido.save(
        update_fields=['estado', 'estado_pago', 'total_pago', 'fecha_completado', 'fecha_envio']
    )
    return pedido


def _bloquear(pedido: Pedido) -> Pedido:
    return Pedido.objects.select_for_update().get(pk=pedido.pk)
