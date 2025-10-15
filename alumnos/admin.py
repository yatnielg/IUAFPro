# app/admin.py
from django.contrib import admin
from django.http import HttpResponse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
import csv

from .models import (
    Financiamiento,
    Pais, Estado,
    Programa,
    InformacionEscolar,
    Alumno,
    ConceptoPago, Cargo, Pago,
    Sede,
    DocumentosAlumno,
)

# ========= util: acción para exportar CSV =========
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
            val = getattr(obj, f)
            # Mostrar __str__ de FKs
            if hasattr(val, "__str__"):
                try:
                    row.append(str(val))
                except Exception:
                    row.append(val)
            else:
                row.append(val)
        writer.writerow(row)
    return response

exportar_csv.short_description = "Exportar selección a CSV"


# --- debajo de exportar_csv ---
from django.conf import settings
from django.contrib import messages
from django.db import transaction
def borrar_toda_info_escolar(modeladmin, request, queryset):
    """
    ⚠️ DEBUG/DEV ONLY: borra TODA la InformacionEscolar y
    limpia la relación desde Alumno.informacionEscolar.
    Ignora el queryset seleccionado a propósito (borra todo).
    """
    if not request.user.is_superuser:
        messages.error(request, "Solo un superusuario puede ejecutar esta acción.")
        return

    if not getattr(settings, "DEBUG", False):
        messages.error(request, "Solo disponible con DEBUG=True.")
        return

    try:
        with transaction.atomic():
            # Desasociar alumnos para evitar on_delete=PROTECT / referencias colgantes
            n_alumnos = Alumno.objects.filter(informacionEscolar__isnull=False).update(informacionEscolar=None)
            # Borrar toda la información escolar
            deleted_count, _ = InformacionEscolar.objects.all().delete()
        messages.success(
            request,
            f"Listo. Alumnos desasociados: {n_alumnos}. Registros InformacionEscolar borrados: {deleted_count}."
        )
    except Exception as e:
        messages.error(request, f"Error al borrar: {e}")

borrar_toda_info_escolar.short_description = "🧨 BORRAR TODA la Información Escolar (DEBUG)"


# ========= PAISES / ESTADOS =========
class EstadoInline(admin.TabularInline):
    model = Estado
    extra = 0
    show_change_link = True


@admin.register(Pais)
class PaisAdmin(admin.ModelAdmin):
    list_display = ("nombre", "flag", "codigo_iso2", "codigo_iso3", "requiere_estado")
    list_filter = ("requiere_estado",)
    search_fields = ("nombre", "codigo_iso2", "codigo_iso3")
    inlines = [EstadoInline]
    actions = [exportar_csv]

    @admin.display(description="Bandera")
    def flag(self, obj):
        return obj.flag_emoji()


@admin.register(Estado)
class EstadoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "pais")
    list_filter = ("pais",)
    search_fields = ("nombre", "pais__nombre")
    autocomplete_fields = ("pais",)
    actions = [exportar_csv]


# ========= SEDE =========
@admin.register(Sede)
class SedeAdmin(admin.ModelAdmin):
    list_display = ("nombre", "pais", "estado", "activo")
    list_filter = ("activo", "pais", "estado")
    search_fields = ("nombre", "pais__nombre", "estado__nombre")
    autocomplete_fields = ("pais", "estado")
    actions = [exportar_csv]


# ========= PROGRAMAS / FINANCIAMIENTO =========
@admin.register(Financiamiento)
class FinanciamientoAdmin(admin.ModelAdmin):
    list_display = ("beca",)
    search_fields = ("beca",)
    actions = [exportar_csv]


@admin.register(Programa)
class ProgramaAdmin(admin.ModelAdmin):
    list_display = (
        "codigo", "nombre", "meses_programa",
        "colegiatura", "inscripcion", "reinscripcion",
        "equivalencia", "titulacion", "activo",
    )
    list_filter = ("activo",)
    search_fields = ("codigo", "nombre")
    actions = [exportar_csv]


# ========= INFORMACION ESCOLAR =========
@admin.register(InformacionEscolar)
class InformacionEscolarAdmin(admin.ModelAdmin):
    list_display = (
        "num_alumno", "programa", "sede", "modalidad",
        "precio_colegiatura", "monto_descuento", "precio_final",
        "meses_programa", "numero_reinscripciones",
        "fin_programa", "creado_en",
    )
    list_filter = ("modalidad", "programa", "sede")
    search_fields = (
        "programa__codigo", "programa__nombre",
        "sede__nombre", "sede__pais__nombre",
    )
    autocomplete_fields = ("programa", "financiamiento", "sede")
    readonly_fields = ("creado_en", "actualizado_en", "precio_final", "fecha_alta")
    actions = [exportar_csv, borrar_toda_info_escolar]  # <- aquí
    #actions = [exportar_csv]  # <- aquí


# ========= INLINES para ALUMNO =========
class DocumentosAlumnoInline(admin.StackedInline):
    model = DocumentosAlumno
    can_delete = False
    extra = 0


class InformacionEscolarInline(admin.StackedInline):
    """
    Si quieres que el Plan se gestione desde el Alumno.
    (Tu modelo Alumno ya tiene OneToOne a InformacionEscolar)
    """
    model = InformacionEscolar
    fk_name = "alumno"  # NOTA: InformacionEscolar no tiene FK directo a Alumno. Si prefieres no usar este inline, comenta esta clase.
    extra = 0
    # Si no tienes FK a Alumno en InformacionEscolar, DEJA ESTA CLASE COMENTADA.


class CargoInline(admin.TabularInline):
    model = Cargo
    extra = 0
    autocomplete_fields = ("concepto",)
    fields = ("concepto", "monto", "fecha_cargo", "fecha_vencimiento", "folio", "pagado")
    show_change_link = True


class PagoInline(admin.TabularInline):
    model = Pago
    extra = 0
    autocomplete_fields = ("cargo",)
    fields = ("fecha", "monto", "metodo", "banco", "referencia", "descripcion", "conciliado", "cargo")
    show_change_link = True


# ========= ALUMNO =========
@admin.register(Alumno)
class AlumnoAdmin(admin.ModelAdmin):
    list_display = (
        "numero_estudiante", "nombre_completo",
        "curp", "sexo",
        "pais", "estado",
        "email", "telefono",
        "programa_display", "sede_display",
        "creado_en",
    )
    list_filter = ("sexo", "pais", "estado")
    search_fields = (
        "numero_estudiante", "nombre", "apellido_p", "apellido_m",
        "curp", "email", "telefono",
        "informacionEscolar__programa__codigo",
        "informacionEscolar__programa__nombre",
        "informacionEscolar__sede__nombre",
    )
    autocomplete_fields = ("pais", "estado", "user", "informacionEscolar")
    readonly_fields = ("creado_en", "actualizado_en")
    inlines = [DocumentosAlumnoInline, CargoInline, PagoInline]
    actions = [exportar_csv]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related(
            "pais", "estado", "informacionEscolar__programa", "informacionEscolar__sede"
        )

    @admin.display(description="Nombre completo")
    def nombre_completo(self, obj: Alumno):
        ap = f" {obj.apellido_p}" if obj.apellido_p else ""
        am = f" {obj.apellido_m}" if obj.apellido_m else ""
        return f"{obj.nombre}{ap}{am}".strip()

    @admin.display(description="Programa")
    def programa_display(self, obj: Alumno):
        ie = getattr(obj, "informacionEscolar", None)
        if ie and ie.programa:
            return f"{ie.programa.codigo} — {ie.programa.nombre}"
        return "—"

    @admin.display(description="Sede")
    def sede_display(self, obj: Alumno):
        ie = getattr(obj, "informacionEscolar", None)
        if ie and ie.sede:
            return str(ie.sede)
        return "—"


# ========= CONCEPTOS / CARGOS / PAGOS =========
@admin.register(ConceptoPago)
class ConceptoPagoAdmin(admin.ModelAdmin):
    list_display = ("codigo", "nombre", "recurrente")
    list_filter = ("recurrente",)
    search_fields = ("codigo", "nombre")
    actions = [exportar_csv]


@admin.register(Cargo)
class CargoAdmin(admin.ModelAdmin):
    list_display = ("id", "alumno", "concepto", "monto", "fecha_cargo", "fecha_vencimiento", "pagado")
    list_filter = ("pagado", "concepto")
    search_fields = ("alumno__numero_estudiante", "alumno__nombre", "alumno__apellido_p", "folio")
    autocomplete_fields = ("alumno", "concepto")
    actions = [exportar_csv]


@admin.register(Pago)
class PagoAdmin(admin.ModelAdmin):
    list_display = ("id", "alumno", "fecha", "monto", "metodo", "banco", "conciliado", "cargo")
    list_filter = ("conciliado", "metodo", "banco")
    search_fields = ("alumno__numero_estudiante", "alumno__nombre", "alumno__apellido_p", "referencia", "descripcion")
    autocomplete_fields = ("alumno", "cargo")
    actions = [exportar_csv]


# ========= DOCUMENTOS (si deseas gestionarlos también aparte) =========
@admin.register(DocumentosAlumno)
class DocumentosAlumnoAdmin(admin.ModelAdmin):
    list_display = ("alumno", "total_subidos", "fecha_ultima_actualizacion", "vista_rapida")
    search_fields = ("alumno__numero_estudiante", "alumno__nombre", "alumno__apellido_p")
    autocomplete_fields = ("alumno",)
    readonly_fields = ("fecha_ultima_actualizacion",)

    def vista_rapida(self, obj):
        # Muestra “chips” de cuáles están subidos
        parts = []
        campos = [
            ("acta_nacimiento", "Acta"),
            ("curp", "CURP"),
            ("certificado_estudios", "Cert."),
            ("titulo_grado", "Título"),
            ("solicitud_registro", "Solicitud"),
            ("validacion_autenticidad", "Validación"),
            ("carta_compromiso", "Compromiso"),
            ("carta_interes", "Interés"),
            ("identificacion_oficial", "ID"),
            ("otro_documento", "Otro"),
        ]
        for fname, label in campos:
            if getattr(obj, fname):
                parts.append(f"<span style='padding:2px 6px;border-radius:8px;background:#e6f4ea;margin-right:4px'>{label}</span>")
        return format_html("".join(parts) or "—")
    vista_rapida.short_description = "Documentos subidos"
