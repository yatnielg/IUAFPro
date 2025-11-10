# app/admin.py
from django.contrib import admin, messages
from django.db import transaction
from django.utils.html import format_html
from django.http import HttpResponse
from django.urls import reverse
from django import forms
import csv

from .models import (
    Financiamiento, Pais, Estado, Programa, InformacionEscolar, Alumno,
    ConceptoPago, Cargo, Pago, ReinscripcionHito,  Sede, PagoDiario, UserProfile,
    MovimientoBanco, DocumentoTipo, ProgramaDocumentoRequisito, DocumentoAlumno,
    ContadorAlumno, ClipCredential, ClipPaymentOrder, TwilioConfig
)

# =============================
# CONFIG BÁSICA
# =============================
admin.site.site_header = "Sistema IUAFPro"
admin.site.site_title = "IUAFPro — Admin"
admin.site.index_title = "Panel de administración"

# =============================
# ACCIÓN GENÉRICA: BORRAR TODO
# =============================
@admin.action(description="🧨 BORRAR TODO (este modelo)")
def borrar_todo_modelo(modeladmin, request, queryset):
    if not request.user.is_superuser:
        messages.error(request, "Solo un superusuario puede ejecutar esta acción.")
        return
    Model = modeladmin.model
    try:
        with transaction.atomic():
            borrados, _ = Model.objects.all().delete()
        messages.success(request, f"Se eliminaron {borrados} registro(s) de {Model._meta.verbose_name_plural}.")
    except Exception as e:
        messages.error(request, f"Error al eliminar todo: {e}")

# =============================
# UTILIDAD EXPORTAR CSV
# =============================
def exportar_csv(modeladmin, request, queryset):
    meta = modeladmin.model._meta
    field_names = [f.name for f in meta.fields]

    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{meta.model_name}.csv"'
    writer = csv.writer(response)
    writer.writerow(field_names)
    for obj in queryset:
        row = []
        for f in field_names:
            val = getattr(obj, f, "")
            try:
                row.append(str(val))
            except Exception:
                row.append(val)
        writer.writerow(row)
    return response
exportar_csv.short_description = "Exportar selección a CSV"

# =============================
# PAISES / ESTADOS
# =============================
class EstadoInline(admin.TabularInline):
    model = Estado
    extra = 0

@admin.register(Pais)
class PaisAdmin(admin.ModelAdmin):
    list_display = ("nombre", "codigo_iso2", "codigo_iso3", "requiere_estado")
    search_fields = ("nombre", "codigo_iso2", "codigo_iso3")
    inlines = [EstadoInline]
    actions = [exportar_csv, borrar_todo_modelo]

@admin.register(Estado)
class EstadoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "pais")
    list_filter = ("pais",)
    search_fields = ("nombre", "pais__nombre")
    actions = [exportar_csv, borrar_todo_modelo]

# =============================
# SEDE
# =============================
@admin.register(Sede)
class SedeAdmin(admin.ModelAdmin):
    list_display = ("nombre", "pais", "estado", "activo")
    list_filter = ("activo", "pais", "estado")
    search_fields = ("nombre", "pais__nombre", "estado__nombre")
    actions = [exportar_csv, borrar_todo_modelo]

# =============================
# FINANCIAMIENTO / PROGRAMAS
# =============================
class FinanciamientoForm(forms.ModelForm):
    class Meta:
        model = Financiamiento
        fields = "__all__"

    def clean(self):
        cleaned = super().clean()
        tipo = cleaned.get("tipo_descuento")
        if tipo == "porcentaje":
            cleaned["monto_descuento"] = None
        elif tipo == "monto":
            cleaned["porcentaje_descuento"] = None
        else:
            cleaned["monto_descuento"] = None
            cleaned["porcentaje_descuento"] = None
        return cleaned

@admin.register(Financiamiento)
class FinanciamientoAdmin(admin.ModelAdmin):
    form = FinanciamientoForm
    list_display = ("beca", "tipo_descuento", "porcentaje_descuento", "monto_descuento")
    list_filter = ("tipo_descuento",)
    search_fields = ("beca",)
    actions = [exportar_csv, borrar_todo_modelo]

@admin.register(Programa)
class ProgramaAdmin(admin.ModelAdmin):
    list_display = ("codigo", "nombre", "meses_programa", "colegiatura", "activo")
    list_filter = ("activo",)
    search_fields = ("codigo", "nombre")
    actions = [exportar_csv, borrar_todo_modelo]

# =============================
# INFORMACION ESCOLAR
# =============================
# ——— Acciones opcionales ———
@admin.action(description="Marcar 'Bienvenida enviada' en los seleccionados")
def marcar_bienvenida(modeladmin, request, queryset):
    updated = queryset.update(
        bienvenida_enviada=True,
        bienvenida_enviada_en=timezone.now(),
        bienvenida_enviada_por=request.user
    )
    modeladmin.message_user(request, f"Se marcaron {updated} registros como 'bienvenida enviada'.")

@admin.action(description="Desmarcar 'Bienvenida enviada' en los seleccionados")
def desmarcar_bienvenida(modeladmin, request, queryset):
    updated = queryset.update(
        bienvenida_enviada=False,
        bienvenida_enviada_en=None,
        bienvenida_enviada_por=None
    )
    modeladmin.message_user(request, f"Se desmarcaron {updated} registros.")

from .models import Grupo
@admin.register(Grupo)
class GrupoAdmin(admin.ModelAdmin):
    list_display = ("programa", "codigo", "nombre", "activo")
    list_filter = ("programa", "activo")
    search_fields = ("codigo", "nombre", "programa__codigo", "programa__nombre")



from django.utils.html import format_html

# --- Filtro útil: ¿tiene grupo nuevo?
class TieneGrupoNuevoFilter(admin.SimpleListFilter):
    title = "Tiene grupo (nuevo)"
    parameter_name = "tiene_grupo_nuevo"

    def lookups(self, request, model_admin):
        return (
            ("si", "Sí"),
            ("no", "No"),
        )

    def queryset(self, request, queryset):
        v = self.value()
        if v == "si":
            return queryset.exclude(grupo_nuevo__isnull=True)
        if v == "no":
            return queryset.filter(grupo_nuevo__isnull=True)
        return queryset


@admin.register(InformacionEscolar)
class InformacionEscolarAdmin(admin.ModelAdmin):
    # -----------------------
    # Presentación principal
    # -----------------------
    list_display = (
        "grupo_display",            # <- muestra el nuevo si existe; si no, el legacy
        "programa", "sede",
        "estatus_academico", "estatus_administrativo",
        "precio_final",
        "bienvenida_enviada", "bienvenida_enviada_en", "bienvenida_enviada_por",
        "creado_en",
    )

    # -----------------------
    # Filtros
    # -----------------------
    list_filter = (
        "programa", "sede",
        "estatus_academico", "estatus_administrativo",
        "bienvenida_enviada",
        "grupo_nuevo",              # por relación al nuevo modelo
        TieneGrupoNuevoFilter,      # sí/no
    )

    # -----------------------
    # Búsquedas
    # -----------------------
    search_fields = (
        "programa__codigo", "programa__nombre",
        "sede__nombre",
        "estatus_academico__nombre", "estatus_administrativo__nombre",
        "alumno__numero_estudiante", "alumno__nombre", "alumno__apellido_p", "alumno__apellido_m",
        "grupo",                    # legacy
        "grupo_nuevo__nombre",      # nuevo
        "grupo_nuevo__codigo",      # nuevo
    )

    # -----------------------
    # Campos de solo lectura
    # -----------------------
    readonly_fields = (
        "creado_en", "actualizado_en",
        "bienvenida_enviada", "bienvenida_enviada_en", "bienvenida_enviada_por",
        "grupo_mostrado_preview",   # vista previa amigable
    )

    # -----------------------
    # Autocomplete y performance
    # -----------------------
    autocomplete_fields = ("programa", "financiamiento", "sede", "grupo_nuevo")
    list_select_related = ("programa", "sede", "estatus_academico", "estatus_administrativo", "grupo_nuevo")

    date_hierarchy = "creado_en"
    ordering = ("-creado_en",)

    # Mantén tus acciones previas
    actions = [exportar_csv, borrar_todo_modelo, marcar_bienvenida, desmarcar_bienvenida]

    # -----------------------
    # Fieldsets (opcional, ordenado)
    # -----------------------
    fieldsets = (
        ("Programa y sede", {
            "fields": ("programa", "sede", "modalidad", "matricula")
        }),
        ("Grupo", {
            "fields": (
                "grupo_nuevo",            # nuevo (FK)
                "grupo",                  # legacy (CharField)
                "grupo_mostrado_preview", # solo lectura
            ),
            "description": "Si 'Grupo (nuevo)' está vacío, se mostrará el valor de 'Grupo' (legacy).",
        }),
        ("Finanzas", {
            "fields": (
                "financiamiento",
                "precio_colegiatura", "monto_descuento", "precio_final",
                "precio_inscripcion", "precio_reinscripcion", "precio_titulacion", "precio_equivalencia",
                "meses_programa", "numero_reinscripciones",
            )
        }),
        ("Fechas", {"fields": ("inicio_programa", "fin_programa", "fecha_alta")}),
        ("Estatus", {"fields": ("estatus_academico", "estatus_administrativo", "requiere_datos_de_facturacion")}),
        ("Sistema", {"fields": ("creado_en", "actualizado_en", "bienvenida_enviada", "bienvenida_enviada_en", "bienvenida_enviada_por")}),
    )

    # -----------------------
    # Queryset optimizado
    # -----------------------
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related(
            "programa", "sede", "estatus_academico", "estatus_administrativo", "grupo_nuevo"
        )

    # -----------------------
    # Columnas y previews
    # -----------------------
    @admin.display(description="Grupo", ordering="grupo_nuevo__nombre")
    def grupo_display(self, obj):
        """
        Lista: prioriza el nombre del grupo nuevo, si no hay muestra el legacy.
        """
        val = (obj.grupo_nuevo.nombre if getattr(obj, "grupo_nuevo_id", None) else None) or (obj.grupo or "")
        # Tip visual: gris si es legacy
        if obj.grupo_nuevo_id:
            return val
        return format_html('<span style="color:#888;">{}</span>', val or "—")

    @admin.display(description="Grupo mostrado (preview)")
    def grupo_mostrado_preview(self, obj):
        return (obj.grupo_nuevo.nombre if getattr(obj, "grupo_nuevo_id", None) else None) or (obj.grupo or "")

# =============================
# ALUMNOS
# =============================
class CargoInline(admin.TabularInline):
    model = Cargo
    extra = 0
    autocomplete_fields = ("concepto",)

class PagoInline(admin.TabularInline):
    model = Pago
    extra = 0
    autocomplete_fields = ("cargo",)

@admin.register(Alumno)
class AlumnoAdmin(admin.ModelAdmin):
    list_display = (
        "numero_estudiante", "nombre", "apellido_p", "apellido_m",
        "curp", "email", "telefono", "programa_display", "sede_display"
    )
    list_filter = ("pais", "estado")
    search_fields = (
        "numero_estudiante", "nombre", "apellido_p", "apellido_m",
        "curp", "email", "telefono",
        "informacionEscolar__programa__codigo", "informacionEscolar__programa__nombre",
        "informacionEscolar__sede__nombre",
    )
    autocomplete_fields = ("pais", "estado", "informacionEscolar")
    inlines = [CargoInline, PagoInline]
    actions = [exportar_csv, borrar_todo_modelo]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("pais", "estado", "informacionEscolar__programa", "informacionEscolar__sede")

    def programa_display(self, obj):
        ie = getattr(obj, "informacionEscolar", None)
        return str(ie.programa) if ie and ie.programa else "—"
    programa_display.short_description = "Programa"

    def sede_display(self, obj):
        ie = getattr(obj, "informacionEscolar", None)
        return str(ie.sede) if ie and ie.sede else "—"
    sede_display.short_description = "Sede"

# =============================
# CONCEPTOS / CARGOS / PAGOS
# =============================
@admin.register(ConceptoPago)
class ConceptoPagoAdmin(admin.ModelAdmin):
    list_display = ("codigo", "nombre", "recurrente")
    list_filter = ("recurrente",)
    search_fields = ("codigo", "nombre")
    actions = [exportar_csv, borrar_todo_modelo]

@admin.register(Cargo)
class CargoAdmin(admin.ModelAdmin):
    list_display = ("alumno", "concepto", "monto", "fecha_cargo", "fecha_vencimiento", "pagado")
    list_filter = ("pagado", "concepto")
    search_fields = (
        "alumno__numero_estudiante", "alumno__nombre", "alumno__apellido_p", "alumno__apellido_m", "folio"
    )
    autocomplete_fields = ("alumno", "concepto")
    actions = [exportar_csv, borrar_todo_modelo]

@admin.register(Pago)
class PagoAdmin(admin.ModelAdmin):
    list_display = ("alumno", "fecha", "monto", "metodo", "banco", "conciliado", "cargo")
    list_filter = ("conciliado", "metodo", "banco")
    search_fields = ("alumno__numero_estudiante", "alumno__nombre", "alumno__apellido_p", "referencia", "descripcion")
    autocomplete_fields = ("alumno", "cargo")
    actions = [exportar_csv, borrar_todo_modelo]

# =============================
# PAGOS DIARIOS
# =============================
@admin.register(PagoDiario)
class PagoDiarioAdmin(admin.ModelAdmin):
    list_display = (
        "fecha", "folio", "monto", "forma_pago", "concepto", "programa",
        "sede", "curp", "numero_alumno", "alumno_link", "mov_banco_link", "creado_en",
    )
    list_display_links = ("fecha", "folio")
    date_hierarchy = "fecha"
    ordering = ("-fecha", "-creado_en")

    list_filter = (("fecha", admin.DateFieldListFilter), "programa", "sede", "forma_pago", ("alumno", admin.EmptyFieldListFilter))
    search_fields = (
        "folio", "nombre", "curp", "programa", "concepto", "pago_detalle",
        "no_auto", "emision", "numero_alumno",
        "alumno__numero_estudiante", "alumno__nombre", "alumno__apellido_p", "alumno__apellido_m",
    )

    list_select_related = ("alumno", "movimiento")
    autocomplete_fields = ("alumno",)
    readonly_fields = ("creado_en", "actualizado_en")
    actions = ("vincular_alumno_por_numero", "desvincular_alumno", exportar_csv, borrar_todo_modelo)

    @admin.display(description="Alumno", ordering="alumno__numero_estudiante", empty_value="—")
    def alumno_link(self, obj: PagoDiario):
        if not obj.alumno_id:
            return "—"
        url = reverse("admin:alumnos_alumno_change", args=[obj.alumno_id])
        a = obj.alumno
        texto = f"{a.numero_estudiante} — {a.nombre} {a.apellido_p or ''} {a.apellido_m or ''}".strip()
        return format_html('<a href="{}">{}</a>', url, texto)

    @admin.display(description="Movimiento banco", ordering="movimiento__id", empty_value="—")
    def mov_banco_link(self, obj: PagoDiario):
        if not obj.movimiento_id:
            return "—"
        url = reverse("admin:alumnos_movimientobanco_change", args=[obj.movimiento_id])
        return format_html('<a href="{}">#{}</a>', url, obj.movimiento_id)

    @admin.action(description="Vincular alumno usando 'numero_alumno'")
    def vincular_alumno_por_numero(self, request, queryset):
        from .models import Alumno
        to_update = queryset.filter(alumno__isnull=True).exclude(numero_alumno__isnull=True)
        count = 0
        for p in to_update:
            try:
                a = Alumno.objects.get(numero_estudiante=p.numero_alumno)
            except Alumno.DoesNotExist:
                continue
            p.alumno = a
            if not p.nombre:
                p.nombre = f"{a.nombre} {a.apellido_p or ''} {a.apellido_m or ''}".strip()
            if not p.curp:
                p.curp = a.curp or p.curp
            p.save(update_fields=["alumno", "nombre", "curp", "actualizado_en"])
            count += 1
        self.message_user(request, f"{count} pagos vinculados a su Alumno por número.")

    @admin.action(description="Desvincular Alumno")
    def desvincular_alumno(self, request, queryset):
        updated = queryset.update(alumno=None)
        self.message_user(request, f"{updated} pagos desvinculados del Alumno.")

    def save_model(self, request, obj, form, change):
        if not obj.alumno_id and obj.numero_alumno:
            from .models import Alumno
            try:
                obj.alumno = Alumno.objects.get(numero_estudiante=obj.numero_alumno)
            except Alumno.DoesNotExist:
                pass
        super().save_model(request, obj, form, change)

# =============================
# MOVIMIENTOS BANCARIOS
# =============================
@admin.register(MovimientoBanco)
class MovimientoBancoAdmin(admin.ModelAdmin):
    list_display = (
        "id", "fecha", "signo_display", "monto", "tipo", "emisor_nombre",
        "nombre_detectado", "nombre_detectado_save", "alumno_link", "pago_link",
        "conciliado", "conciliado_por", "conciliado_en",
        "institucion_emisora", "sucursal", "referencia_numerica", "autorizacion",
    )
    list_display_links = ("id", "fecha")
    list_filter = ("conciliado", "signo", "tipo", "institucion_emisora", "sucursal", "source_sheet_name")
    search_fields = (
        "emisor_nombre", "referencia_alfanumerica", "concepto",
        "referencia_numerica", "autorizacion", "institucion_emisora", "descripcion_raw",
        "alumno_asignado__numero_estudiante", "alumno_asignado__nombre", "alumno_asignado__apellido_p", "alumno_asignado__apellido_m", "alumno_asignado__curp",
    )
    date_hierarchy = "fecha"
    ordering = ("-fecha", "id")
    list_select_related = ("alumno_asignado", "pago_creado", "conciliado_por")
    readonly_fields = ("uid_hash", "created_at", "updated_at", "nombre_detectado", "pago_creado", "conciliado_por", "conciliado_en")
    autocomplete_fields = ("alumno_asignado",)

    actions = ("marcar_conciliado", "desmarcar_conciliado", exportar_csv, borrar_todo_modelo)

    def marcar_conciliado(self, request, qs):
        updated = qs.update(conciliado=True, conciliado_por=request.user)
        self.message_user(request, f"{updated} movimientos marcados como conciliados.")
    marcar_conciliado.short_description = "Marcar como conciliado"

    def desmarcar_conciliado(self, request, qs):
        updated = qs.update(conciliado=False, conciliado_por=None, conciliado_en=None, pago_creado=None, alumno_asignado=None)
        self.message_user(request, f"{updated} movimientos desmarcados (se limpiaron vínculos).")
    desmarcar_conciliado.short_description = "Desmarcar conciliado (limpiar vínculos)"

    def signo_display(self, obj):
        if obj.signo == 1:
            return format_html('<span style="color:#2e7d32;font-weight:600">Abono</span>')
        if obj.signo == -1:
            return format_html('<span style="color:#c62828;font-weight:600">Cargo</span>')
        return "-"
    signo_display.short_description = "Signo"
    signo_display.admin_order_field = "signo"

    def alumno_link(self, obj):
        if not obj.alumno_asignado_id:
            return "-"
        url = reverse("admin:alumnos_alumno_change", args=[obj.alumno_asignado_id])
        a = obj.alumno_asignado
        nombre = f"{a.numero_estudiante} — {a.nombre} {a.apellido_p} {a.apellido_m}".strip()
        return format_html('<a href="{}">{}</a>', url, nombre)
    alumno_link.short_description = "Alumno"

    def pago_link(self, obj):
        if not obj.pago_creado_id:
            return "-"
        url = reverse("admin:alumnos_pagodiario_change", args=[obj.pago_creado_id])
        return format_html('<a href="{}">Pago #{}</a>', url, obj.pago_creado_id)
    pago_link.short_description = "Pago"

    def save_model(self, request, obj, form, change):
        if "conciliado" in form.changed_data:
            if obj.conciliado:
                from django.utils import timezone
                obj.conciliado_por = request.user
                obj.conciliado_en = timezone.now()
            else:
                obj.conciliado_por = None
                obj.conciliado_en = None
        super().save_model(request, obj, form, change)

# =============================
# NUEVO SISTEMA DE DOCUMENTOS
# =============================
@admin.register(DocumentoTipo)
class DocumentoTipoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "slug", "presentacion", "orden", "multiple", "activo")
    list_editable = ("orden", "activo")
    list_filter = ("activo", "multiple")
    search_fields = ("nombre", "slug", "presentacion", "observaciones")
    ordering = ("orden", "nombre")
    prepopulated_fields = {"slug": ("nombre",)}
    actions = [exportar_csv, borrar_todo_modelo]

@admin.register(ProgramaDocumentoRequisito)
class ProgramaDocumentoRequisitoAdmin(admin.ModelAdmin):
    list_display = ("programa", "tipo", "obligatorio", "minimo", "maximo", "activo")
    list_filter = ("programa", "tipo", "obligatorio", "activo")
    search_fields = ("programa__nombre", "programa__codigo", "tipo__nombre", "tipo__slug")
    actions = [exportar_csv, borrar_todo_modelo]

@admin.register(DocumentoAlumno)
class DocumentoAlumnoAdmin(admin.ModelAdmin):
    list_display = ("info_escolar", "tipo", "archivo", "valido", "verificado_por", "verificado_en", "creado_en")
    list_filter = ("tipo", "valido")
    search_fields = (
        "info_escolar__alumno__numero_estudiante",
        "info_escolar__alumno__nombre",
        "info_escolar__alumno__apellido_p",
        "tipo__nombre",
    )
    actions = [exportar_csv, borrar_todo_modelo]

# =============================
# CONTADORES, CLIP Y TWILIO
# =============================
@admin.register(ContadorAlumno)
class ContadorAlumnoAdmin(admin.ModelAdmin):
    list_display = ("llave", "ultimo_numero")
    search_fields = ("llave",)
    actions = [exportar_csv, borrar_todo_modelo]

@admin.register(ClipCredential)
class ClipCredentialAdmin(admin.ModelAdmin):
    list_display = ("name", "is_sandbox", "active", "updated_at")
    list_filter = ("is_sandbox", "active")
    search_fields = ("name", "public_key")
    actions = [exportar_csv, borrar_todo_modelo]

@admin.register(ClipPaymentOrder)
class ClipPaymentOrderAdmin(admin.ModelAdmin):
    list_display = ("id", "alumno", "amount", "currency", "status", "clip_payment_id", "created_at")
    list_filter = ("status", "currency")
    search_fields = ("id", "clip_payment_id", "description")
    actions = [exportar_csv, borrar_todo_modelo]

@admin.register(TwilioConfig)
class TwilioConfigAdmin(admin.ModelAdmin):
    list_display = ("name", "env", "active", "updated_at")
    list_filter = ("env", "active", "updated_at", "created_at")
    search_fields = ("name", "account_sid", "messaging_service_sid", "sms_from", "whatsapp_from")
    actions = [exportar_csv, borrar_todo_modelo]


# ==========================================================
# usuarios / perfiles (User + UserProfile)
# ==========================================================
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import UserProfile, Sede  # Sede ya está arriba, OK

User = get_user_model()

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "sedes_list", "puede_ver_todo", "puede_editar_todo", "ver_todos_los_pagos")
    list_filter = (
        "puede_ver_todo", "puede_editar_todo", "ver_todos_los_pagos",
        ("sedes", admin.RelatedOnlyFieldListFilter),
    )
    search_fields = ("user__username", "user__first_name", "user__last_name", "user__email", "sedes__nombre")
    autocomplete_fields = ("user",)
    filter_horizontal = ("sedes",)
    ordering = ("user__username",)
    actions = [exportar_csv, borrar_todo_modelo]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("user").prefetch_related("sedes")

    @admin.display(description="Sedes", ordering="sedes__nombre")
    def sedes_list(self, obj: UserProfile):
        nombres = [s.nombre for s in obj.sedes.all()]
        return ", ".join(nombres) if nombres else "—"

class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    fk_name = "user"
    extra = 0
    filter_horizontal = ("sedes",)
    fieldsets = (
            (None, {"fields": ("sedes",)}),
            ("Permisos de alcance", {
                "fields": ("puede_ver_todo", "puede_editar_todo", "ver_todos_los_pagos")
            }),
    )

try:
    admin.site.unregister(User)
except admin.sites.NotRegistered:
    pass

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    inlines = [UserProfileInline]
    actions = ["crear_perfiles_faltantes"]  # No ponemos borrar_todo en usuarios por seguridad

    @admin.action(description="Crear UserProfile a usuarios sin perfil")
    def crear_perfiles_faltantes(self, request, queryset):
        creados = 0
        for u in queryset:
            if not hasattr(u, "profile"):
                UserProfile.objects.create(user=u)
                creados += 1
        self.message_user(request, f"Perfiles creados: {creados}")


# ==========================================================
# UploadInvite (en tu otro admin se usa otro archivo; lo incluimos aquí también)
# ==========================================================
from django.utils import timezone
from .models import UploadInvite

@admin.register(UploadInvite)
class UploadInviteAdmin(admin.ModelAdmin):
    @classmethod
    def _has_field(cls, name: str) -> bool:
        return any(f.name == name for f in UploadInvite._meta.get_fields())

    def get_list_display(self, request):
        cols = ["token_short", "alumno", "public_path", "expires_at", "is_valid_display", "created_by", "created_at"]
        if self._has_field("used_count") or self._has_field("max_uses"):
            cols.insert(4, "uses_display")
        return cols

    list_select_related = ("alumno", "created_by")
    search_fields = ("token", "alumno__numero_estudiante", "alumno__curp", "alumno__nombre", "alumno__apellido_p", "alumno__apellido_m")
    list_filter = ("created_at", "expires_at")
    date_hierarchy = "created_at"
    actions = ("revocar_enlaces", "extender_7_dias", "reiniciar_usos", borrar_todo_modelo)

    def get_readonly_fields(self, request, obj=None):
        ro = ["token", "created_by", "created_at", "public_path", "is_valid_display"]
        if self._has_field("used_count"):
            ro.append("used_count")
        return ro

    def get_fields(self, request, obj=None):
        fields = ["alumno", "token", "public_path"]
        row = ["expires_at"]
        if self._has_field("max_uses"):
            row.append("max_uses")
        if self._has_field("used_count"):
            row.append("used_count")
        fields.append(tuple(row))
        fields += ["is_valid_display", ("created_by", "created_at")]
        return fields

    @admin.display(description="Token")
    def token_short(self, obj: UploadInvite):
        t = obj.token or ""
        return (t[:10] + "…") if len(t) > 10 else t

    @admin.display(description="Ruta pública", ordering="token")
    def public_path(self, obj: UploadInvite):
        url = reverse("public_upload", args=[obj.token])
        return format_html('<code>{}</code>', url)

    @admin.display(description="Usos")
    def uses_display(self, obj: UploadInvite):
        if self._has_field("used_count") and self._has_field("max_uses"):
            max_ = getattr(obj, "max_uses", 0)
            used = getattr(obj, "used_count", 0)
            return f"{used} / {('∞' if not max_ else max_)}"
        elif self._has_field("used_count"):
            return str(getattr(obj, "used_count", 0))
        elif self._has_field("max_uses"):
            max_ = getattr(obj, "max_uses", 0)
            return f"0 / {('∞' if not max_ else max_)}"
        return "—"

    @admin.display(boolean=True, description="Vigente")
    def is_valid_display(self, obj: UploadInvite):
        return self._is_valid(obj)

    @admin.action(description="Revocar (expira ahora)")
    def revocar_enlaces(self, request, queryset):
        ahora = timezone.now()
        updated = queryset.update(expires_at=ahora)
        self.message_user(request, f"{updated} enlace(s) revocado(s).")

    @admin.action(description="Extender 7 días")
    def extender_7_dias(self, request, queryset):
        n = 0
        for inv in queryset:
            base = inv.expires_at or timezone.now()
            inv.expires_at = base + timezone.timedelta(days=7)
            inv.save(update_fields=["expires_at"])
            n += 1
        self.message_user(request, f"{n} enlace(s) extendido(s) 7 días.")

    @admin.action(description="Reiniciar contador de usos")
    def reiniciar_usos(self, request, queryset):
        if not self._has_field("used_count"):
            self.message_user(request, "Tu modelo no tiene 'used_count'. Nada que reiniciar.", level=20)
            return
        updated = queryset.update(used_count=0)
        self.message_user(request, f"Contador reiniciado en {updated} enlace(s).")

    def _is_valid(self, obj: UploadInvite) -> bool:
        not_expired = (obj.expires_at is None) or (obj.expires_at > timezone.now())
        if self._has_field("max_uses") and self._has_field("used_count"):
            has_uses = (getattr(obj, "max_uses", 0) == 0) or (getattr(obj, "used_count", 0) < getattr(obj, "max_uses", 0))
        else:
            has_uses = True
        return bool(not_expired and has_uses)

    def save_model(self, request, obj, form, change):
        if not change and not getattr(obj, "created_by", None) and request.user.is_authenticated:
            try:
                obj.created_by = request.user
            except Exception:
                pass
        super().save_model(request, obj, form, change)


# =============================
# ESTATUS (BaseEstatus)
# =============================
from .models import EstatusAcademico, EstatusAdministrativo

class BaseEstatusAdmin(admin.ModelAdmin):
    list_display = ("orden", "nombre", "codigo", "activo")
    list_display_links = ("nombre",)
    list_editable = ("orden", "activo")
    list_filter = ("activo",)
    search_fields = ("nombre", "codigo")
    ordering = ("orden", "nombre")
    actions = (borrar_todo_modelo,)  # también disponible aquí

    readonly_fields: tuple = ()

    def get_readonly_fields(self, request, obj=None):
        if obj:
            return self.readonly_fields + ("codigo",)
        return self.readonly_fields

    def activar(self, request, queryset):
        updated = queryset.update(activo=True)
        self.message_user(request, f"{updated} estatus activados.")
    activar.short_description = "Activar seleccionados"

    def desactivar(self, request, queryset):
        updated = queryset.update(activo=False)
        self.message_user(request, f"{updated} estatus desactivados.")
    desactivar.short_description = "Desactivar seleccionados"

@admin.register(EstatusAcademico)
class EstatusAcademicoAdmin(BaseEstatusAdmin):
    pass

@admin.register(EstatusAdministrativo)
class EstatusAdministrativoAdmin(BaseEstatusAdmin):
    pass


@admin.register(ReinscripcionHito)
class ReinscripcionHitoAdmin(admin.ModelAdmin):
    list_display = ("programa", "meses_offset", "monto", "activo", "nombre")
    list_filter  = ("activo", "programa")
    search_fields = ("programa__codigo", "programa__nombre", "nombre")