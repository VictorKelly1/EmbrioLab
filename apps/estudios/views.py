from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import FormView, TemplateView

from apps.core.forms import aplicar_errores
from apps.core.mixins import RolRequerido
from apps.cuentas.models import Rol
from apps.estudios.forms import AliasForm, ValorReferenciaForm
from apps.estudios.models import Estudio, EstudioAlias, ValorReferencia
from apps.estudios.selectors import alias_de, catalogo, obtener_estudio, referencias_de
from apps.estudios.services import (
    CAMPOS_REFERENCIA,
    actualizar_alias,
    actualizar_valor_referencia,
    cambiar_activo_referencia,
    eliminar_alias,
    registrar_alias,
    registrar_valor_referencia,
)

# PROVISIONAL (CONTEXTO.md §8): la recepción guarda alias y el químico las referencias.
ROLES_ALIAS = [Rol.RECEPCIONISTA]
ROLES_REFERENCIA = [Rol.QUIMICO]


class EstudioListaView(RolRequerido, TemplateView):
    roles = [Rol.RECEPCIONISTA, Rol.QUIMICO]
    template_name = 'estudios/lista.html'

    def get_template_names(self):
        if self.request.headers.get('HX-Request'):
            return ['estudios/_resultados.html']
        return [self.template_name]

    def get_context_data(self, **kwargs):
        termino = self.request.GET.get('q', '').strip()
        return super().get_context_data(termino=termino, estudios=catalogo(termino), **kwargs)


class EstudioDetalleView(RolRequerido, TemplateView):
    roles = [Rol.RECEPCIONISTA, Rol.QUIMICO]
    template_name = 'estudios/detalle.html'

    def get_context_data(self, **kwargs):
        try:
            estudio = obtener_estudio(self.kwargs['pk'])
        except Estudio.DoesNotExist as error:
            raise Http404 from error
        definicion = estudio.definicion
        referencias = list(referencias_de(estudio))
        for valor in referencias:
            campo = definicion.campo(valor.clave_campo) if definicion else None
            valor.etiqueta_campo = campo.etiqueta if campo else valor.clave_campo
        usuario = self.request.user
        return super().get_context_data(
            estudio=estudio,
            definicion=definicion,
            referencias=referencias,
            alias=alias_de(estudio),
            puede_alias=usuario.tiene_rol(*ROLES_ALIAS),
            puede_referencias=usuario.tiene_rol(*ROLES_REFERENCIA),
            **kwargs,
        )


# Alias


class _AliasFormView(RolRequerido, FormView):
    roles = ROLES_ALIAS
    form_class = AliasForm
    template_name = 'estudios/alias_formulario.html'
    alias = None

    def get_context_data(self, **kwargs):
        return super().get_context_data(alias=self.alias, estudio=self.estudio, **kwargs)

    def form_valid(self, form):
        try:
            self.guardar(form.cleaned_data['estudio'], form.cleaned_data['alias'])
        except ValidationError as error:
            aplicar_errores(form, error)
            return self.form_invalid(form)
        messages.success(self.request, self.mensaje_exito)
        return redirect('estudios:detalle', pk=form.cleaned_data['estudio'].pk)


class AliasCrearView(_AliasFormView):
    mensaje_exito = 'Alias guardado.'

    def dispatch(self, request, *args, **kwargs):
        self.estudio = get_object_or_404(Estudio, pk=kwargs['pk'])
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        return {'estudio': self.estudio}

    def guardar(self, estudio, texto):
        registrar_alias(estudio=estudio, alias=texto, usuario=self.request.user)


class AliasEditarView(_AliasFormView):
    mensaje_exito = 'Alias actualizado.'

    def dispatch(self, request, *args, **kwargs):
        self.alias = get_object_or_404(
            EstudioAlias.objects.select_related('estudio'), pk=kwargs['pk']
        )
        self.estudio = self.alias.estudio
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        return {'alias': self.alias.alias, 'estudio': self.alias.estudio}

    def guardar(self, estudio, texto):
        actualizar_alias(self.alias, estudio=estudio, texto=texto)


class AliasEliminarView(RolRequerido, View):
    roles = ROLES_ALIAS
    http_method_names = ['post']

    def post(self, request, pk):
        alias = get_object_or_404(EstudioAlias, pk=pk)
        estudio_pk = alias.estudio_id
        eliminar_alias(alias)
        messages.success(request, f'Se eliminó el alias «{alias.alias}».')
        return redirect('estudios:detalle', pk=estudio_pk)


# Valores de referencia


class _ReferenciaFormView(RolRequerido, FormView):
    roles = ROLES_REFERENCIA
    form_class = ValorReferenciaForm
    template_name = 'estudios/referencia_formulario.html'
    valor = None

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), 'estudio': self.estudio}

    def get_context_data(self, **kwargs):
        return super().get_context_data(valor=self.valor, estudio=self.estudio, **kwargs)

    def form_valid(self, form):
        datos = form.cleaned_data
        try:
            self.guardar(**datos)
        except ValidationError as error:
            aplicar_errores(form, error)
            return self.form_invalid(form)
        messages.success(self.request, self.mensaje_exito)
        return redirect('estudios:detalle', pk=self.estudio.pk)


class ReferenciaCrearView(_ReferenciaFormView):
    mensaje_exito = 'Valor de referencia guardado.'

    def dispatch(self, request, *args, **kwargs):
        self.estudio = get_object_or_404(Estudio, pk=kwargs['pk'])
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        return {'clave_campo': self.request.GET.get('campo', '')}

    def guardar(self, **datos):
        registrar_valor_referencia(estudio=self.estudio, usuario=self.request.user, **datos)


class ReferenciaEditarView(_ReferenciaFormView):
    mensaje_exito = 'Valor de referencia actualizado.'

    def dispatch(self, request, *args, **kwargs):
        self.valor = get_object_or_404(
            ValorReferencia.objects.select_related('estudio'), pk=kwargs['pk']
        )
        self.estudio = self.valor.estudio
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        return {campo: getattr(self.valor, campo) for campo in CAMPOS_REFERENCIA}

    def guardar(self, **datos):
        actualizar_valor_referencia(self.valor, **datos)


class ReferenciaActivoView(RolRequerido, View):
    roles = ROLES_REFERENCIA
    http_method_names = ['post']

    def post(self, request, pk):
        valor = get_object_or_404(ValorReferencia, pk=pk)
        activo = request.POST.get('activo') == '1'
        cambiar_activo_referencia(valor, activo)
        messages.success(
            request,
            'Valor de referencia reactivado.' if activo else 'Valor de referencia desactivado.',
        )
        return redirect('estudios:detalle', pk=valor.estudio_id)
