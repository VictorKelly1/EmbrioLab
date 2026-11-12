from django.conf import settings
from django.db import models
from django.db.models import Q


class TipoNotificacion(models.TextChoices):
    RECORDATORIO = 'recordatorio', 'Recordatorio de cita'
    QR = 'qr', 'Link del formulario'
    RESULTADOS = 'resultados', 'Resultados'


class Canal(models.TextChoices):
    CORREO = 'correo', 'Correo'
    WHATSAPP = 'whatsapp', 'WhatsApp'


class DestinoTipo(models.TextChoices):
    PACIENTE = 'paciente', 'Paciente'
    DOCTOR = 'doctor', 'Doctor'


class EstadoNotificacion(models.TextChoices):
    PENDIENTE = 'pendiente', 'Pendiente'
    ENVIADO = 'enviado', 'Enviado'
    FALLIDO = 'fallido', 'Fallido'


class Notificacion(models.Model):
    """
    Un envío a un destinatario por un canal (CONTEXTO.md §5, outbox). La crea un servicio
    en la misma transacción que el cambio que la origina; el worker la envía y la marca.

    El mensaje no se guarda: el worker lo arma al enviar (el PDF se genera al vuelo y el
    link del formulario solo existe en claro en ese momento).
    """

    tipo = models.CharField(max_length=12, choices=TipoNotificacion.choices)
    canal = models.CharField(max_length=10, choices=Canal.choices)
    destinatario = models.CharField(max_length=254)
    # A quién va: los resultados también pueden ir al doctor del pedido.
    destino_tipo = models.CharField(
        'destino', max_length=10, choices=DestinoTipo.choices, default=DestinoTipo.PACIENTE
    )
    cita = models.ForeignKey(
        'citas.Cita',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='notificaciones',
    )
    estudio_pedido = models.ForeignKey(
        'pedidos.EstudioPedido',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='notificaciones',
    )
    # Quién lo mandó (cambio del cliente, 2026-11-11). Nulo = automático (el recordatorio)
    # o un envío anterior a este campo.
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='+',
        verbose_name='envió',
    )
    estado = models.CharField(
        max_length=10, choices=EstadoNotificacion.choices, default=EstadoNotificacion.PENDIENTE
    )
    error = models.TextField(blank=True)
    fecha_envio = models.DateTimeField(null=True, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-creado_en', '-id']
        verbose_name = 'notificación'
        verbose_name_plural = 'notificaciones'
        constraints = [
            models.CheckConstraint(
                condition=Q(tipo__in=TipoNotificacion.values), name='notificacion_tipo_valido'
            ),
            models.CheckConstraint(
                condition=Q(canal__in=Canal.values), name='notificacion_canal_valido'
            ),
            models.CheckConstraint(
                condition=Q(destino_tipo__in=DestinoTipo.values),
                name='notificacion_destino_tipo_valido',
            ),
            models.CheckConstraint(
                condition=Q(estado__in=EstadoNotificacion.values),
                name='notificacion_estado_valido',
            ),
            models.CheckConstraint(
                condition=~Q(estado=EstadoNotificacion.ENVIADO) | Q(fecha_envio__isnull=False),
                name='notificacion_enviada_con_fecha',
            ),
        ]

    def __str__(self):
        return f'{self.get_tipo_display()} por {self.get_canal_display()} a {self.destinatario}'
