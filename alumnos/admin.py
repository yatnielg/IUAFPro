# app/admin.py
from django.contrib import admin, messages
from django.db import transaction
from django.utils.html import format_html
from django.http import HttpResponse
from django import forms
import csv

from .models import (
    Financiamiento, Pais, Estado, Programa, InformacionEscolar, Alumno,
    ConceptoPago, Cargo, Pago, Sede, PagoDiario, UserProfile,
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
            # Representar FKs de forma legible
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
    search_fields = ("nombre", "codigo_iso2", "codigo_iso3")  # requerido por AlumnoAdmin.autocomplete_fields
    inlines = [EstadoInline]
    actions = [exportar_csv]

@admin.register(Estado)
class EstadoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "pais")
    list_filter = ("pais",)
    search_fields = ("nombre", "pais__nombre")
    actions = [exportar_csv]

# =============================
# SEDE
# =============================
@admin.register(Sede)
class SedeAdmin(admin.ModelAdmin):
    list_display = ("nombre", "pais", "estado", "activo")
    list_filter = ("activo", "pais", "estado")
    search_fields = ("nombre", "pais__nombre", "estado__nombre")
    actions = [exportar_csv]

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
    actions = [exportar_csv]

@admin.register(Programa)
class ProgramaAdmin(admin.ModelAdmin):
    list_display = ("codigo", "nombre", "meses_programa", "colegiatura", "activo")
    list_filter = ("activo",)
    search_fields = ("codigo", "nombre")
    actions = [exportar_csv]

# =============================
# INFORMACION ESCOLAR
# =============================
@admin.register(InformacionEscolar)
class InformacionEscolarAdmin(admin.ModelAdmin):
    list_display = (
        "programa", "sede", "estatus_academico",
        "estatus_administrativo", "precio_final", "creado_en"
    )
    list_filter = ("programa", "sede", "estatus_academico", "estatus_administrativo")
    search_fields = (  # requerido por AlumnoAdmin.autocomplete_fields
        "programa__codigo", "programa__nombre",
        "sede__nombre",
        "estatus_academico__nombre", "estatus_administrativo__nombre",
        "alumno__numero_estudiante", "alumno__nombre", "alumno__apellido_p", "alumno__apellido_m",
    )
    readonly_fields = ("creado_en", "actualizado_en", "precio_final")
    actions = [exportar_csv]

# =============================
# ALUMNOS
# =============================
class CargoInline(admin.TabularInline):
    model = Cargo
    extra = 0
    autocomplete_fields = ("concepto",)  # requiere search_fields en ConceptoPagoAdmin

class PagoInline(admin.TabularInline):
    model = Pago
    extra = 0
    autocomplete_fields = ("cargo",)     # requiere search_fields en CargoAdmin

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
    actions = [exportar_csv]

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
    search_fields = ("codigo", "nombre")  # requerido por CargoInline.autocomplete_fields
    actions = [exportar_csv]

@admin.register(Cargo)
class CargoAdmin(admin.ModelAdmin):
    list_display = ("alumno", "concepto", "monto", "fecha_cargo", "fecha_vencimiento", "pagado")
    list_filter = ("pagado", "concepto")
    search_fields = (  # requerido por PagoInline.autocomplete_fields
        "alumno__numero_estudiante", "alumno__nombre", "alumno__apellido_p", "alumno__apellido_m", "folio"
    )
    autocomplete_fields = ("alumno", "concepto")
    actions = [exportar_csv]

@admin.register(Pago)
class PagoAdmin(admin.ModelAdmin):
    list_display = ("alumno", "fecha", "monto", "metodo", "banco", "conciliado", "cargo")
    list_filter = ("conciliado", "metodo", "banco")
    search_fields = ("alumno__numero_estudiante", "alumno__nombre", "alumno__apellido_p", "referencia", "descripcion")
    autocomplete_fields = ("alumno", "cargo")
    actions = [exportar_csv]

# =============================
# PAGOS DIARIOS
# =============================
@admin.register(PagoDiario)
class PagoDiarioAdmin(admin.ModelAdmin):
    list_display = ("fecha", "monto", "concepto", "programa", "sede", "numero_alumno")
    list_filter = ("programa", "sede", ("fecha", admin.DateFieldListFilter))
    search_fields = (
        "numero_alumno", "nombre", "curp", "programa", "concepto", "pago_detalle",
        "alumno__numero_estudiante", "alumno__nombre", "alumno__apellido_p", "alumno__apellido_m",
    )
    actions = [exportar_csv]

# =============================
# MOVIMIENTOS BANCARIOS
# =============================
def borrar_todos_mov_banco(modeladmin, request, queryset):
    if not request.user.is_superuser:
        messages.error(request, "Solo un superusuario puede ejecutar esta acción.")
        return
    try:
        with transaction.atomic():
            borrados, _ = MovimientoBanco.objects.all().delete()
        messages.success(request, f"Se eliminaron {borrados} movimientos.")
    except Exception as e:
        messages.error(request, f"Error al eliminar: {e}")
borrar_todos_mov_banco.short_description = "🧨 BORRAR TODOS los movimientos"

@admin.register(MovimientoBanco)
class MovimientoBancoAdmin(admin.ModelAdmin):
    list_display = (
        "fecha", "tipo", "monto", "sucursal", "referencia_numerica",
        "autorizacion", "emisor_nombre", "institucion_emisora", "nombre_detectado"
    )
    list_filter = ("tipo", "institucion_emisora", "sucursal", "source_sheet_name")
    search_fields = ("descripcion_raw", "emisor_nombre", "concepto", "referencia_numerica", "autorizacion", "institucion_emisora")
    date_hierarchy = "fecha"
    actions = [exportar_csv, borrar_todos_mov_banco]

# =============================
# NUEVO SISTEMA DE DOCUMENTOS
# =============================
@admin.register(DocumentoTipo)
class DocumentoTipoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "slug", "multiple", "activo")
    list_filter = ("activo", "multiple")
    search_fields = ("nombre", "slug")

@admin.register(ProgramaDocumentoRequisito)
class ProgramaDocumentoRequisitoAdmin(admin.ModelAdmin):
    list_display = ("programa", "tipo", "obligatorio", "minimo", "maximo", "activo")
    list_filter = ("programa", "tipo", "obligatorio", "activo")
    search_fields = ("programa__nombre", "programa__codigo", "tipo__nombre", "tipo__slug")

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
    actions = [exportar_csv]

# =============================
# CONTADORES, CLIP Y TWILIO
# =============================
@admin.register(ContadorAlumno)
class ContadorAlumnoAdmin(admin.ModelAdmin):
    list_display = ("llave", "ultimo_numero")
    search_fields = ("llave",)

@admin.register(ClipCredential)
class ClipCredentialAdmin(admin.ModelAdmin):
    list_display = ("name", "is_sandbox", "active", "updated_at")
    list_filter = ("is_sandbox", "active")
    search_fields = ("name", "public_key")

@admin.register(ClipPaymentOrder)
class ClipPaymentOrderAdmin(admin.ModelAdmin):
    list_display = ("id", "alumno", "amount", "currency", "status", "clip_payment_id", "created_at")
    list_filter = ("status", "currency")
    search_fields = ("id", "clip_payment_id", "description")

@admin.register(TwilioConfig)
class TwilioConfigAdmin(admin.ModelAdmin):
    list_display = ("name", "env", "active", "updated_at")
    list_filter = ("env", "active", "updated_at", "created_at")
    search_fields = ("name", "account_sid", "messaging_service_sid", "sms_from", "whatsapp_from")



######################################################
# alumnos/admin.py
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import UserProfile, Sede

User = get_user_model()




# --- UserProfile admin estándar ---
@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "sedes_list",
        "puede_ver_todo",
        "puede_editar_todo",
        "ver_todos_los_pagos",
    )
    list_filter = (
        "puede_ver_todo",
        "puede_editar_todo",
        "ver_todos_los_pagos",
        ("sedes", admin.RelatedOnlyFieldListFilter),
    )
    search_fields = (
        "user__username",
        "user__first_name",
        "user__last_name",
        "user__email",
        "sedes__nombre",
    )
    autocomplete_fields = ("user", "sedes")  # usa SedeAdmin.search_fields
    filter_horizontal = ()  # (opcional si prefieres cajas dobles en vez de autocomplete)
    ordering = ("user__username",)

    fieldsets = (
        (None, {
            "fields": ("user", "sedes")
        }),
        ("Permisos de alcance", {
            "fields": (
                "puede_ver_todo",
                "puede_editar_todo",
                "ver_todos_los_pagos",
            )
        }),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("user").prefetch_related("sedes")

    @admin.display(description="Sedes", ordering="sedes__nombre")
    def sedes_list(self, obj: UserProfile):
        nombres = [s.nombre for s in obj.sedes.all()]
        return ", ".join(nombres) if nombres else "—"


# --- Inline para ver/editar el perfil directamente desde el User ---
class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    fk_name = "user"
    extra = 0
    autocomplete_fields = ("sedes",)
    fieldsets = (
        (None, {"fields": ("sedes",)}),
        ("Permisos de alcance", {
            "fields": (
                "puede_ver_todo",
                "puede_editar_todo",
                "ver_todos_los_pagos",
            )
        }),
    )


# Re-registra el User admin con el inline del perfil
try:
    admin.site.unregister(User)
except admin.sites.NotRegistered:
    pass


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    inlines = [UserProfileInline]

    # (Opcional) acción para crear perfiles faltantes
    actions = ["crear_perfiles_faltantes"]

    @admin.action(description="Crear UserProfile a usuarios sin perfil")
    def crear_perfiles_faltantes(self, request, queryset):
        creados = 0
        for u in queryset:
            if not hasattr(u, "profile"):
                UserProfile.objects.create(user=u)
                creados += 1
        self.message_user(request, f"Perfiles creados: {creados}")

##############################################################
# alumnos/admin.py
from django.contrib import admin
from django.utils import timezone
from django.utils.html import format_html
from django.urls import reverse

from .models import UploadInvite


@admin.register(UploadInvite)
class UploadInviteAdmin(admin.ModelAdmin):
    """
    Admin para enlaces seguros de subida de documentos.
    Funciona aunque tu modelo no tenga used_count / max_uses.
    Campos esperados (al menos):
      - alumno (FK a Alumno)
      - token (str, unique)
      - expires_at (DateTimeField, null=True, blank=True)
      - created_by (FK a User, null=True, blank=True)
      - created_at (DateTimeField, auto_now_add=True)
      - (opcionales) max_uses (int), used_count (int)
    """

    # ---- utilidades para detectar campos opcionales ----
    @classmethod
    def _has_field(cls, name: str) -> bool:
        return any(f.name == name for f in UploadInvite._meta.get_fields())

    # ---- list / search / filter ----
    def get_list_display(self, request):
        cols = [
            "token_short",
            "alumno",
            "public_path",
            "expires_at",
            "is_valid_display",
            "created_by",
            "created_at",
        ]
        if self._has_field("used_count") or self._has_field("max_uses"):
            cols.insert(4, "uses_display")
        return cols

    list_select_related = ("alumno", "created_by")
    search_fields = (
        "token",
        "alumno__numero_estudiante",
        "alumno__curp",
        "alumno__nombre",
        "alumno__apellido_p",
        "alumno__apellido_m",
    )
    list_filter = ("created_at", "expires_at")
    date_hierarchy = "created_at"

    # ---- fields / readonly dinámicos ----
    def get_readonly_fields(self, request, obj=None):
        ro = ["token", "created_by", "created_at", "public_path", "is_valid_display"]
        # Solo añadir si existen en el modelo
        if self._has_field("used_count"):
            ro.append("used_count")
        return ro

    def get_fields(self, request, obj=None):
        fields = ["alumno", "token", "public_path"]

        # Fila de expiración/uso
        row = ["expires_at"]
        if self._has_field("max_uses"):
            row.append("max_uses")
        if self._has_field("used_count"):
            row.append("used_count")
        fields.append(tuple(row))

        fields += ["is_valid_display", ("created_by", "created_at")]
        return fields

    actions = ("revocar_enlaces", "extender_7_dias", "reiniciar_usos")

    # --------- displays ---------
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

    # --------- actions ---------
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

    # --------- lógica de vigencia ---------
    def _is_valid(self, obj: UploadInvite) -> bool:
        not_expired = (obj.expires_at is None) or (obj.expires_at > timezone.now())
        # Si no existe max_uses/used_count, asumimos usos ilimitados
        if self._has_field("max_uses") and self._has_field("used_count"):
            has_uses = (getattr(obj, "max_uses", 0) == 0) or (getattr(obj, "used_count", 0) < getattr(obj, "max_uses", 0))
        else:
            has_uses = True
        return bool(not_expired and has_uses)

    # Guardar autor automáticamente al crear
    def save_model(self, request, obj, form, change):
        if not change and not getattr(obj, "created_by", None) and request.user.is_authenticated:
            try:
                obj.created_by = request.user
            except Exception:
                pass
        super().save_model(request, obj, form, change)
