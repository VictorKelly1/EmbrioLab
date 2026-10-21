from django.db.models import Count, Q, QuerySet

from apps.formularios.constructor import respuestas_legibles
from apps.formularios.models import Formulario, FormularioLlenado, VersionFormulario
from apps.pacientes.models import Paciente


def version_para(paciente: Paciente) -> VersionFormulario | None:
    """
    Versión publicada del formulario activo que corresponde al género del paciente.
    Si hay uno específico de su género gana sobre uno para todos.
    """
    versiones = (
        VersionFormulario.objects.select_related('formulario')
        .filter(publicada=True, formulario__activo=True)
        .filter(
            Q(formulario__genero_aplicable=paciente.persona.genero)
            | Q(formulario__genero_aplicable='')
        )
    )
    return min(
        versiones,
        key=lambda v: (v.formulario.genero_aplicable == '', v.formulario.nombre),
        default=None,
    )


def listar_formularios() -> QuerySet[Formulario]:
    return Formulario.objects.annotate(
        num_llenados=Count('versiones__llenados'),
    ).prefetch_related('versiones')


def version_publicada(formulario: Formulario) -> VersionFormulario | None:
    return next((v for v in formulario.versiones.all() if v.publicada), None)


def llenados_recientes(limite: int = 20) -> QuerySet[FormularioLlenado]:
    return FormularioLlenado.objects.select_related(
        'cita__paciente__persona', 'version_formulario__formulario'
    ).order_by('-fecha_llenado')[:limite]


def respuestas_de(llenado: FormularioLlenado) -> list[dict]:
    return respuestas_legibles(llenado.version_formulario.esquema, llenado.respuestas)
