import re

from django.db.models import Prefetch, QuerySet

from apps.pacientes.models import Doctor, Paciente
from apps.personas.models import Contacto
from apps.personas.selectors import filtrar_por_nombre

# Sin espacios y con al menos un dígito entre letras: parece el inicio de una CURP.
_PARECE_CURP = re.compile(r'^[A-Za-z]{4}[A-Za-z0-9]*$')


def _pacientes() -> QuerySet[Paciente]:
    return Paciente.objects.select_related('persona').prefetch_related(
        Prefetch('persona__contactos', queryset=Contacto.objects.filter(principal=True))
    )


def buscar_pacientes(termino: str = '', *, incluir_inactivos: bool = False) -> QuerySet[Paciente]:
    """
    Busca por número de paciente (solo dígitos), por CURP (o su inicio) o por nombre.
    Sin término, devuelve los más recientes primero.
    """
    pacientes = _pacientes()
    if not incluir_inactivos:
        pacientes = pacientes.activos()

    termino = termino.strip()
    if not termino:
        return pacientes
    if termino.isdigit():
        return pacientes.filter(numero=int(termino))
    if _PARECE_CURP.match(termino) and any(c.isdigit() for c in termino):
        return pacientes.filter(persona__curp__startswith=termino.upper())
    return filtrar_por_nombre(pacientes, termino, campo='persona__nombre_busqueda')


def obtener_paciente(pk: int) -> Paciente:
    return _pacientes().select_related('persona__direccion').get(pk=pk)


def buscar_doctores(termino: str = '') -> QuerySet[Doctor]:
    doctores = Doctor.objects.all()
    for palabra in termino.split():
        doctores = doctores.filter(nombre__icontains=palabra)
    return doctores
