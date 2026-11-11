from django.conf import settings
from django.db import models
from django.db.models import Q


class EstadoEstudio(models.TextChoices):
    PENDIENTE = 'pendiente', 'Pendiente'
    EN_PROCESO = 'en_proceso', 'En proceso'
    COMPLETADO = 'completado', 'Completado'


class EstadoPago(models.TextChoices):
    PENDIENTE = 'pendiente', 'Pendiente'
    ABONADO = 'abonado', 'Abonado'
    PAGADO = 'pagado', 'Pagado'


class EstadoPedido(models.TextChoices):
    PENDIENTE = 'pendiente', 'Pendiente'
    EN_PROCESO = 'en_proceso', 'En proceso'
    COMPLETADO = 'completado', 'Completado'


class ConsecutivoPedido(models.Model):
    """Último número de pedido dado en cada año (pedidos/numero.py)."""

    anio = models.PositiveSmallIntegerField(primary_key=True)
    ultimo = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = 'consecutivo de pedido'
        verbose_name_plural = 'consecutivos de pedido'

    def __str__(self):
        return f'{self.anio}: {self.ultimo}'


class Pedido(models.Model):
    """
    Una orden del doctor dentro de una cita (una cita puede tener varios).
    `estado`, `estado_pago`, `total_pago`, `fecha_completado` y `fecha_envio` son
    derivados: SOLO los escribe `services.recalcular_pedido` (CONTEXTO.md §3).
    """

    cita = models.ForeignKey('citas.Cita', on_delete=models.PROTECT, related_name='pedidos')
    recepcionista = models.ForeignKey(
        'cuentas.Recepcionista', on_delete=models.PROTECT, related_name='pedidos'
    )
    doctor = models.ForeignKey(
        'pacientes.Doctor', null=True, blank=True, on_delete=models.PROTECT, related_name='pedidos'
    )
    numero = models.CharField('número', max_length=20, unique=True)
    fecha_inicio = models.DateTimeField(auto_now_add=True)
    estado = models.CharField(
        max_length=12, choices=EstadoPedido.choices, default=EstadoPedido.PENDIENTE
    )
    estado_pago = models.CharField(
        max_length=10, choices=EstadoPago.choices, default=EstadoPago.PENDIENTE
    )
    total_pago = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    fecha_completado = models.DateTimeField(null=True, blank=True)
    fecha_envio = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-fecha_inicio']
        constraints = [
            models.CheckConstraint(
                condition=Q(estado__in=EstadoPedido.values), name='pedido_estado_valido'
            ),
            models.CheckConstraint(
                condition=Q(estado_pago__in=EstadoPago.values), name='pedido_estado_pago_valido'
            ),
        ]

    def __str__(self):
        return f'Pedido {self.numero}'


class EstudioPedido(models.Model):
    """
    Un estudio de un pedido. Máquina de estados en pedidos/estados.py:
    pendiente → en_proceso → completado; "enviado" = `fecha_envio` no nula.
    Pendiente = en la cola de los químicos, sin encargado. Un químico lo toma y queda
    como su único encargado mientras está en proceso (CONTEXTO.md §3).
    """

    pedido = models.ForeignKey(Pedido, on_delete=models.PROTECT, related_name='estudios')
    estudio = models.ForeignKey(
        'estudios.Estudio', on_delete=models.PROTECT, related_name='estudios_pedido'
    )
    # Como lo escribió el doctor en la orden.
    nombre_solicitado = models.CharField(max_length=150)
    # Copias al momento del pedido: si el catálogo cambia, el pedido no.
    precio = models.DecimalField(max_digits=10, decimal_places=2)
    version_estudio = models.PositiveIntegerField()
    # El químico que tomó el estudio de la cola y cuándo.
    quimico_encargado = models.ForeignKey(
        'cuentas.Quimico',
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='estudios_encargados',
    )
    fecha_toma = models.DateTimeField(null=True, blank=True)
    estado = models.CharField(
        max_length=12, choices=EstadoEstudio.choices, default=EstadoEstudio.PENDIENTE
    )
    estado_pago = models.CharField(
        max_length=10, choices=EstadoPago.choices, default=EstadoPago.PENDIENTE
    )
    resultados = models.JSONField(null=True, blank=True)
    quimico_completo = models.ForeignKey(
        'cuentas.Quimico',
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='estudios_completados',
    )
    fecha_completado = models.DateTimeField(null=True, blank=True)
    usuario_envio = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name='+'
    )
    fecha_envio = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['pedido', 'id']
        verbose_name = 'estudio de pedido'
        verbose_name_plural = 'estudios de pedido'
        indexes = [
            models.Index(fields=['estado'], name='estudio_pedido_estado_idx'),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(estado__in=EstadoEstudio.values), name='estudio_pedido_estado_valido'
            ),
            models.CheckConstraint(
                condition=Q(estado_pago__in=EstadoPago.values),
                name='estudio_pedido_estado_pago_valido',
            ),
            models.CheckConstraint(
                condition=Q(precio__gte=0), name='estudio_pedido_precio_no_negativo'
            ),
            models.CheckConstraint(
                condition=~Q(estado=EstadoEstudio.COMPLETADO)
                | Q(fecha_completado__isnull=False, resultados__isnull=False),
                name='estudio_pedido_completado_con_resultados',
            ),
            # Pendiente = en la cola, sin encargado; en proceso siempre tiene uno.
            models.CheckConstraint(
                condition=Q(
                    estado=EstadoEstudio.PENDIENTE,
                    quimico_encargado__isnull=True,
                    fecha_toma__isnull=True,
                )
                | Q(
                    estado=EstadoEstudio.EN_PROCESO,
                    quimico_encargado__isnull=False,
                    fecha_toma__isnull=False,
                )
                | Q(estado=EstadoEstudio.COMPLETADO),
                name='estudio_pedido_encargado_segun_estado',
            ),
            # Solo se envía lo completado.
            models.CheckConstraint(
                condition=Q(fecha_envio__isnull=True) | Q(estado=EstadoEstudio.COMPLETADO),
                name='estudio_pedido_envio_solo_completado',
            ),
        ]

    def __str__(self):
        return f'{self.pedido.numero} · {self.estudio}'

    @property
    def enviado(self) -> bool:
        return self.fecha_envio is not None


class ObservacionPedido(models.Model):
    """
    Nota libre de la recepción sobre un pedido (p. ej. «enviar los resultados juntos»).
    Un pedido tiene las que hagan falta; solo se agregan (CONTEXTO.md §8).
    """

    pedido = models.ForeignKey(Pedido, on_delete=models.CASCADE, related_name='observaciones')
    texto = models.TextField(max_length=500)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+'
    )
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['pedido', 'fecha', 'id']
        verbose_name = 'observación de pedido'
        verbose_name_plural = 'observaciones de pedido'
        constraints = [
            models.CheckConstraint(
                condition=~Q(texto=''), name='observacion_pedido_texto_no_vacio'
            ),
        ]

    def __str__(self):
        return f'{self.pedido.numero}: {self.texto[:40]}'
