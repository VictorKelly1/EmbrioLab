from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from apps.core.models import ModeloConTiempos
from apps.estudios.definiciones import obtener
from apps.personas.models import Genero


class CategoriaEstudio(models.Model):
    """Sanguíneos, Esperma, Cultivo y Otros (CONTEXTO.md §1)."""

    nombre = models.CharField(max_length=100, unique=True)

    class Meta:
        ordering = ['id']
        verbose_name = 'categoría de estudio'
        verbose_name_plural = 'categorías de estudio'

    def __str__(self):
        return self.nombre


class Estudio(ModeloConTiempos):
    """
    Fila del catálogo. Los campos y cálculos viven en código, en la definición con la
    misma `clave` (apps/estudios/definiciones/). Los estudios no se crean desde el sistema.
    """

    clave = models.CharField(max_length=30, unique=True)
    nombre = models.CharField(max_length=150)
    categoria = models.ForeignKey(
        CategoriaEstudio, on_delete=models.PROTECT, related_name='estudios'
    )
    # Precio vigente. Cada estudio de un pedido copia el suyo al momento de pedirse.
    precio = models.DecimalField(max_digits=10, decimal_places=2)
    version_definicion = models.PositiveIntegerField(default=1)
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ['categoria', 'nombre']
        constraints = [
            models.CheckConstraint(condition=Q(precio__gte=0), name='estudio_precio_no_negativo'),
        ]

    def __str__(self):
        return self.nombre

    @property
    def definicion(self):
        return obtener(self.clave)


class EstudioAlias(models.Model):
    """El nombre que usa un doctor en su orden → el estudio del catálogo."""

    estudio = models.ForeignKey(Estudio, on_delete=models.CASCADE, related_name='alias')
    # Normalizado (sin acentos, minúsculas, espacios simples): lo hace el servicio.
    alias = models.CharField(max_length=150, unique=True)
    usuario_registro = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+'
    )
    fecha_registro = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['alias']
        verbose_name = 'alias de estudio'
        verbose_name_plural = 'alias de estudios'

    def __str__(self):
        return f'{self.alias} → {self.estudio}'


class ValorReferencia(models.Model):
    """
    PROVISIONAL (CONTEXTO.md §4). Rango normal de un campo del estudio, opcionalmente por
    género y edad (años cumplidos, ambos límites incluidos). Vacío = aplica a todos.
    Al completar un estudio, la referencia usada se copia en sus resultados (`como_json`).
    """

    estudio = models.ForeignKey(
        Estudio, on_delete=models.PROTECT, related_name='valores_referencia'
    )
    clave_campo = models.CharField(max_length=50)
    genero = models.CharField(max_length=10, choices=Genero.choices, blank=True, default='')
    edad_minima = models.PositiveSmallIntegerField(null=True, blank=True)
    edad_maxima = models.PositiveSmallIntegerField(null=True, blank=True)
    valor_minimo = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    valor_maximo = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    texto_referencia = models.CharField(max_length=200, blank=True)
    unidad = models.CharField(max_length=30, blank=True)
    activo = models.BooleanField(default=True)
    vigente_desde = models.DateField(default=timezone.localdate)
    usuario_registro = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+'
    )

    class Meta:
        ordering = ['estudio', 'clave_campo', 'genero', 'edad_minima', '-vigente_desde']
        verbose_name = 'valor de referencia'
        verbose_name_plural = 'valores de referencia'
        constraints = [
            models.CheckConstraint(
                condition=Q(valor_minimo__isnull=False)
                | Q(valor_maximo__isnull=False)
                | ~Q(texto_referencia=''),
                name='referencia_con_valor',
            ),
            models.CheckConstraint(
                condition=Q(valor_minimo__isnull=True)
                | Q(valor_maximo__isnull=True)
                | Q(valor_minimo__lte=F('valor_maximo')),
                name='referencia_rango_valido',
            ),
            models.CheckConstraint(
                condition=Q(edad_minima__isnull=True)
                | Q(edad_maxima__isnull=True)
                | Q(edad_minima__lte=F('edad_maxima')),
                name='referencia_edades_validas',
            ),
        ]

    def __str__(self):
        return f'{self.estudio.clave}.{self.clave_campo}: {self.rango}'

    def clean(self):
        errores = {}
        if self.valor_minimo is None and self.valor_maximo is None and not self.texto_referencia:
            errores['texto_referencia'] = (
                'Escriba un valor mínimo, un máximo o un texto de referencia.'
            )
        if (
            self.valor_minimo is not None
            and self.valor_maximo is not None
            and self.valor_minimo > self.valor_maximo
        ):
            errores['valor_maximo'] = 'El máximo no puede ser menor que el mínimo.'
        if (
            self.edad_minima is not None
            and self.edad_maxima is not None
            and self.edad_minima > self.edad_maxima
        ):
            errores['edad_maxima'] = 'La edad máxima no puede ser menor que la mínima.'
        if errores:
            raise ValidationError(errores)

    @property
    def rango(self) -> str:
        """'70 – 99 mg/dL', '≥ 40 mg/dL', '≤ 200 mg/dL' o el texto."""
        minimo, maximo = _numero(self.valor_minimo), _numero(self.valor_maximo)
        if minimo and maximo:
            texto = f'{minimo} – {maximo}'
        elif minimo:
            texto = f'≥ {minimo}'
        elif maximo:
            texto = f'≤ {maximo}'
        else:
            return self.texto_referencia
        return f'{texto} {self.unidad}'.strip()

    @property
    def aplica_a(self) -> str:
        """'Hombres · 18 a 60 años', 'Mujeres', 'Todos'."""
        partes = []
        if self.genero:
            partes.append({'masculino': 'Hombres', 'femenino': 'Mujeres'}[self.genero])
        if self.edad_minima is not None and self.edad_maxima is not None:
            partes.append(f'{self.edad_minima} a {self.edad_maxima} años')
        elif self.edad_minima is not None:
            partes.append(f'{self.edad_minima} años o más')
        elif self.edad_maxima is not None:
            partes.append(f'hasta {self.edad_maxima} años')
        return ' · '.join(partes) or 'Todos'

    def como_json(self) -> dict:
        """La copia que se guarda dentro de los resultados al completar el estudio."""
        return {
            'id': self.pk,
            'valor_minimo': _numero(self.valor_minimo) or None,
            'valor_maximo': _numero(self.valor_maximo) or None,
            'texto': self.texto_referencia,
            'unidad': self.unidad,
            'rango': self.rango,
            'vigente_desde': self.vigente_desde.isoformat(),
        }


def _numero(valor: Decimal | None) -> str:
    """Decimal sin ceros sobrantes: 40.0000 → '40', 1.5000 → '1.5'. None → ''."""
    if valor is None:
        return ''
    return f'{Decimal(str(valor)).normalize():f}'
