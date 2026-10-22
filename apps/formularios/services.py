from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from apps.citas.models import Cita
from apps.citas.services import consumir_token
from apps.formularios.esquema import validar_esquema
from apps.formularios.models import Formulario, FormularioLlenado, VersionFormulario


@transaction.atomic
def crear_formulario(
    *, nombre: str, descripcion: str = '', genero_aplicable: str = '', usuario=None
) -> Formulario:
    formulario = Formulario(
        nombre=nombre.strip(),
        descripcion=descripcion.strip(),
        genero_aplicable=genero_aplicable,
        usuario_creador=usuario,
    )
    formulario.full_clean()
    formulario.save()
    return formulario


@transaction.atomic
def publicar_version(formulario: Formulario, esquema: dict) -> VersionFormulario:
    """Crea la versión siguiente con el esquema, la publica y despublica la anterior."""
    validar_esquema(esquema)
    # Bloquea el formulario para que dos publicaciones simultáneas no choquen.
    Formulario.objects.select_for_update().get(pk=formulario.pk)
    ultima = formulario.versiones.aggregate(n=Max('numero_version'))['n'] or 0
    formulario.versiones.filter(publicada=True).update(publicada=False)
    return VersionFormulario.objects.create(
        formulario=formulario,
        numero_version=ultima + 1,
        esquema=esquema,
        publicada=True,
        fecha_publicacion=timezone.now(),
    )


@transaction.atomic
def guardar_respuestas(
    cita: Cita, version: VersionFormulario, respuestas: dict
) -> FormularioLlenado:
    """Guarda las respuestas y consume el token: el link ya no sirve otra vez."""
    cita = Cita.objects.select_for_update().get(pk=cita.pk)
    if FormularioLlenado.objects.filter(cita=cita).exists():
        raise ValidationError('El formulario de esta cita ya se llenó.')
    llenado = FormularioLlenado.objects.create(
        cita=cita, version_formulario=version, respuestas=respuestas
    )
    consumir_token(cita)
    return llenado
