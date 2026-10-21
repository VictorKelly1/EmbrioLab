from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.core.validators import RegexValidator
from django.db import models
from django.db.models.functions import Lower

from apps.core.models import ModeloBorradoLogico, ModeloConTiempos


class Rol(models.TextChoices):
    ADMIN = 'admin', 'Administrador'
    RECEPCIONISTA = 'recepcionista', 'Recepcionista'
    QUIMICO = 'quimico', 'Químico'


class UsuarioManager(BaseUserManager):
    def get_by_natural_key(self, correo):
        return self.get(correo__iexact=correo)

    def create_user(self, correo, password=None, **campos):
        if not correo:
            raise ValueError('El correo es obligatorio.')
        usuario = self.model(correo=correo.strip().lower(), **campos)
        usuario.set_password(password)
        usuario.save(using=self._db)
        return usuario

    def create_superuser(self, correo, password=None, **campos):
        campos.setdefault('is_staff', True)
        campos.setdefault('is_superuser', True)
        return self.create_user(correo, password, **campos)


class Usuario(AbstractBaseUser, PermissionsMixin, ModeloConTiempos):
    """AUTH_USER_MODEL. El login es con el correo."""

    persona = models.OneToOneField(
        'personas.Persona', on_delete=models.PROTECT, related_name='usuario'
    )
    nombre_usuario = models.CharField(max_length=50, blank=True)  # provisional
    correo = models.EmailField(unique=True)
    color = models.CharField(
        max_length=7,
        default='#B57EDC',
        validators=[RegexValidator(r'^#[0-9A-Fa-f]{6}$', 'Usa un color hexadecimal: #RRGGBB.')],
    )
    is_active = models.BooleanField('activo', default=True)
    is_staff = models.BooleanField('acceso al admin de Django', default=False)

    objects = UsuarioManager()

    USERNAME_FIELD = 'correo'
    EMAIL_FIELD = 'correo'
    REQUIRED_FIELDS = ['persona']

    class Meta:
        constraints = [
            models.UniqueConstraint(Lower('correo'), name='usuario_correo_unico_sin_mayusculas'),
        ]

    def __str__(self):
        return self.correo

    @property
    def roles(self) -> set[str]:
        """Roles activos. En la Fase 1 hay uno solo, pero la BD permite varios."""
        roles = set()
        for rol, modelo in MODELOS_ROL.items():
            fila = getattr(self, modelo._meta.model_name, None)
            if fila is not None and fila.estado_actividad:
                roles.add(rol)
        return roles

    def tiene_rol(self, *roles: str) -> bool:
        return self.is_active and bool(self.roles.intersection(roles))


class ModeloRol(ModeloBorradoLogico):
    usuario = models.OneToOneField(Usuario, on_delete=models.PROTECT, related_name='+')
    fecha_registro = models.DateField(auto_now_add=True)
    sueldo = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        abstract = True

    def __str__(self):
        return str(self.usuario)


class Admin(ModeloRol):
    usuario = models.OneToOneField(Usuario, on_delete=models.PROTECT, related_name='admin')

    class Meta:
        verbose_name = 'administrador'
        verbose_name_plural = 'administradores'


class Recepcionista(ModeloRol):
    usuario = models.OneToOneField(Usuario, on_delete=models.PROTECT, related_name='recepcionista')


class Quimico(ModeloRol):
    usuario = models.OneToOneField(Usuario, on_delete=models.PROTECT, related_name='quimico')
    cedula_profesional = models.CharField('cédula profesional', max_length=20)

    class Meta:
        verbose_name = 'químico'


MODELOS_ROL = {Rol.ADMIN: Admin, Rol.RECEPCIONISTA: Recepcionista, Rol.QUIMICO: Quimico}
