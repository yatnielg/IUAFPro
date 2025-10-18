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
    PagoDiario,
    UserProfile,
)

admin.site.site_header = "Sistema IUAFPro"
admin.site.site_title  = "IUAFPro — Admin"
admin.site.index_title = "Panel de administración"

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
from django import forms
class FinanciamientoForm(forms.ModelForm):
    class Meta:
        model = Financiamiento
        fields = "__all__"

    def clean(self):
        """
        Opcional: además de la validación del modelo, ‘limpia’ el campo
        que no aplica según tipo_descuento para que quede bonito en BD.
        """
        cleaned = super().clean()
        tipo = cleaned.get("tipo_descuento")

        if tipo == "porcentaje":
            # Si es porcentaje, asegúrate de vaciar monto
            cleaned["monto_descuento"] = None
        elif tipo == "monto":
            # Si es monto, vacía porcentaje
            cleaned["porcentaje_descuento"] = None
        else:  # ninguno
            cleaned["monto_descuento"] = None
            cleaned["porcentaje_descuento"] = None

        return cleaned



@admin.register(Financiamiento)
class FinanciamientoAdmin(admin.ModelAdmin):
    form = FinanciamientoForm

    list_display = (
        "beca",
        "tipo_descuento",
        "porcentaje_descuento",
        "monto_descuento",
    )
    list_filter = ("tipo_descuento",)
    search_fields = ("beca",)

    fieldsets = (
        (None, {
            "fields": ("beca", "tipo_descuento")
        }),
        ("Valores de descuento", {
            "fields": ("porcentaje_descuento", "monto_descuento"),
            "description": "Completa SOLO el campo que corresponda al tipo de descuento."
        }),
    )

    # Incluye un JS simple para mostrar/ocultar campos según el tipo:
    class Media:
        js = ("admin/financiamiento_toggle.js",)


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
def borrar_todos_alumnos(modeladmin, request, queryset):
    """
    ⚠️ Elimina TODOS los registros de Alumno, ignorando la selección.
    Antes, borra los archivos físicos de DocumentosAlumno para no dejar basura en el storage.
    Usa con mucha precaución.
    """
    if not request.user.is_superuser:
        messages.error(request, "Solo un superusuario puede ejecutar esta acción.")
        return

    from .models import Alumno, DocumentosAlumno  # import local para evitar ciclos

    try:
        with transaction.atomic():
            # 1) Borrar archivos de DocumentosAlumno
            total_archivos = 0
            campos_file = [
                "acta_nacimiento", "curp", "certificado_estudios", "titulo_grado",
                "solicitud_registro", "validacion_autenticidad", "carta_compromiso",
                "carta_interes", "identificacion_oficial", "otro_documento",
            ]

            for doc in DocumentosAlumno.objects.select_related("alumno").all():
                for campo in campos_file:
                    f = getattr(doc, campo, None)
                    if f:
                        try:
                            f.delete(save=False)  # elimina del storage sin tocar DB
                            total_archivos += 1
                        except Exception:
                            # Si falla un archivo, continúa con los demás
                            pass

            # 2) Borrar todos los alumnos (on_delete=CASCADE limpiará el resto)
            borrados, _ = Alumno.objects.all().delete()

        messages.success(
            request,
            f"Se eliminaron TODOS los alumnos ({borrados}) y {total_archivos} archivo(s) de documentos."
        )
    except Exception as e:
        messages.error(request, f"Error al eliminar: {e}")

borrar_todos_alumnos.short_description = "🧨 BORRAR TODOS los alumnos (incluye archivos de documentos)"


@admin.register(Alumno)
class AlumnoAdmin(admin.ModelAdmin):
    list_display = (
        "numero_estudiante", "nombre_completo",
        "curp", "sexo",
        "pais", "estado",
        "email_institucional", "email_preferido",
        "email", "telefono",
        "programa_display", "sede_display",
        "creado_en",
    )
    actions = [exportar_csv, borrar_todos_alumnos]  # ← aquí agregada
    list_filter = ("sexo", "pais", "estado")
    search_fields = (
        "numero_estudiante", "nombre", "apellido_p", "apellido_m",
        "curp", "email", "telefono","email_institucional",
        "informacionEscolar__programa__codigo",
        "informacionEscolar__programa__nombre",
        "informacionEscolar__sede__nombre",
    )
    autocomplete_fields = ("pais", "estado", "user", "informacionEscolar")
    readonly_fields = ("creado_en", "actualizado_en")
    inlines = [DocumentosAlumnoInline, CargoInline, PagoInline]
   

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
def borrar_todos_documentos(modeladmin, request, queryset):
    """
    ⚠️ Elimina TODOS los registros de DocumentosAlumno, ignorando la selección,
    y borra los archivos físicos de los FileField.
    Usa con mucha precaución.
    """
    from .models import DocumentosAlumno  # evita import circular

    if not request.user.is_superuser:
        messages.error(request, "Solo un superusuario puede ejecutar esta acción.")
        return

    # (Opcional) resguardar para entornos dev
    # if not getattr(settings, "DEBUG", False):
    #     messages.error(request, "Solo disponible con DEBUG=True.")
    #     return

    try:
        with transaction.atomic():
            total_archivos = 0
            campos_file = [
                "acta_nacimiento", "curp", "certificado_estudios", "titulo_grado",
                "solicitud_registro", "validacion_autenticidad", "carta_compromiso",
                "carta_interes", "identificacion_oficial", "otro_documento",
            ]

            # Borra archivos de cada fila
            for doc in DocumentosAlumno.objects.all():
                for campo in campos_file:
                    f = getattr(doc, campo, None)
                    if f:
                        try:
                            f.delete(save=False)  # elimina del storage sin tocar DB
                            total_archivos += 1
                        except Exception:
                            # Si falla algún archivo, seguimos con los demás
                            pass

            # Borra todos los registros de la tabla
            borrados, _ = DocumentosAlumno.objects.all().delete()

        messages.success(
            request,
            f"Se eliminaron todos los DocumentosAlumno ({borrados} filas) y {total_archivos} archivo(s)."
        )
    except Exception as e:
        messages.error(request, f"Error al eliminar: {e}")

borrar_todos_documentos.short_description = "🧨 BORRAR TODOS los DocumentosAlumno (incluye archivos)"


@admin.register(DocumentosAlumno)
class DocumentosAlumnoAdmin(admin.ModelAdmin):
    list_display = ("alumno", "total_subidos", "fecha_ultima_actualizacion", "vista_rapida")
    search_fields = ("alumno__numero_estudiante", "alumno__nombre", "alumno__apellido_p")
    autocomplete_fields = ("alumno",)
    readonly_fields = ("fecha_ultima_actualizacion",)

    actions = [exportar_csv, borrar_todos_documentos]  # ← agrega aquí la acción

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


#########################################################################################


class AsociadoFilter(admin.SimpleListFilter):
    title = "¿Asociado a alumno?"
    parameter_name = "asociado"

    def lookups(self, request, model_admin):
        return (
            ("si", "Sí"),
            ("no", "No"),
        )

    def queryset(self, request, queryset):
        if self.value() == "si":
            return queryset.filter(alumno__isnull=False)
        if self.value() == "no":
            return queryset.filter(alumno__isnull=True)
        return queryset





def borrar_todos_pagos(modeladmin, request, queryset):
    """
    ⚠️ Elimina TODOS los registros de PagoDiario, ignorando la selección.
    Usa con precaución.
    """
    if not request.user.is_superuser:
        messages.error(request, "Solo un superusuario puede ejecutar esta acción.")
        return

    try:
        with transaction.atomic():
            total = PagoDiario.objects.all().delete()
        messages.success(request, f"Se eliminaron todos los registros de PagoDiario ({total[0]} filas).")
    except Exception as e:
        messages.error(request, f"Error al eliminar: {e}")

borrar_todos_pagos.short_description = "🧨 BORRAR TODOS los registros de PagoDiario"

@admin.register(PagoDiario)
class PagoDiarioAdmin(admin.ModelAdmin):
    date_hierarchy = "fecha"
    ordering = ("-fecha", "-id")

    list_display = (
        "folio", "fecha", "monto", "concepto", "pago_detalle",
        "programa", "sede", "forma_pago", "curp",
        "numero_alumno", "alumno_link",
        "emision",
    )
    list_select_related = ("alumno",)

    search_fields = (
        "folio", "nombre", "curp", "programa", "concepto", "pago_detalle",
        "sede", "no_auto",
        "numero_alumno",
        "alumno__numero_estudiante", "alumno__nombre", "alumno__apellido_p", "alumno__apellido_m",
    )
    list_filter = (
        AsociadoFilter,
        "sede",
        "programa",
        "concepto",
        "forma_pago",
        "emision",
        ("fecha", admin.DateFieldListFilter),
    )

    readonly_fields = ("creado_en", "actualizado_en")
    fields = (
        "folio", "fecha", "monto", "forma_pago",
        "concepto", "pago_detalle", "programa",
        "sede", "no_auto", "curp", "numero_alumno",
        "nombre", "emision",
        "alumno",
        "creado_en", "actualizado_en",
    )

    raw_id_fields = ("alumno",)

    actions = ("asociar_por_numero_alumno", "desasociar_alumno", borrar_todos_pagos)
    #actions = ("asociar_por_numero_alumno", "desasociar_alumno")


    def alumno_link(self, obj):
        if not obj.alumno:
            return "—"
        return f"{obj.alumno.numero_estudiante} — {obj.alumno.nombre}"
    alumno_link.short_description = "Alumno"

    # --- ACCIONES ---

    def asociar_por_numero_alumno(self, request, queryset):
        """
        Si la fila tiene numero_alumno y existe un Alumno con ese pk,
        se asocia. No pisa asociaciones existentes.
        """
        asociados = 0
        no_encontrado = 0
        ya_asociado = 0
        for pago in queryset:
            if pago.alumno_id:
                ya_asociado += 1
                continue
            num = pago.numero_alumno
            if not num:
                no_encontrado += 1
                continue
            alumno = Alumno.objects.filter(pk=num).first()
            if alumno:
                pago.alumno = alumno
                pago.save(update_fields=["alumno"])
                asociados += 1
            else:
                no_encontrado += 1
        self.message_user(
            request,
            f"Asociados: {asociados} | Ya asociados: {ya_asociado} | Sin alumno/No encontrado: {no_encontrado}"
        )
    asociar_por_numero_alumno.short_description = "Asociar por 'No.Alumno' (si existe)"

    def desasociar_alumno(self, request, queryset):
        rows = queryset.update(alumno=None)
        self.message_user(request, f"Desasociados {rows} pagos.")
    desasociar_alumno.short_description = "Desasociar alumno"


# (Opcional) Ver pagos desde el admin de Alumno como inline
class PagoDiarioInline(admin.TabularInline):
    model = PagoDiario
    extra = 0
    fields = ("fecha", "monto", "concepto", "pago_detalle", "programa", "forma_pago", "folio")
    readonly_fields = fields

# En alumnos/admin.py puedes añadir:
# from django.contrib import admin
# from .models import Alumno
# from pagos.admin import PagoDiarioInline
#
# @admin.register(Alumno)
# class AlumnoAdmin(admin.ModelAdmin):
#     inlines = [PagoDiarioInline]
#     ...
########################################################################
# app/admin.py

from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

#from .models import UserProfile

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "puede_ver_todo",
        "puede_editar_todo",
        "ver_todos_los_pagos",   # <- nuevo
        "sedes_list",
    )
    list_filter = (
        "puede_ver_todo",
        "puede_editar_todo",
        "ver_todos_los_pagos",   # <- nuevo
        "sedes",
    )
    search_fields = (
        "user__username",
        "user__email",
        "user__first_name",
        "user__last_name",
    )
    filter_horizontal = ("sedes",)

    fieldsets = (
        (None, {
            "fields": ("user", "sedes"),
        }),
        ("Permisos", {
            "fields": ("puede_ver_todo", "puede_editar_todo", "ver_todos_los_pagos"),
            "description": (
                "• <b>puede_ver_todo</b>: puede ver todos los alumnos/sedes.<br>"
                "• <b>puede_editar_todo</b>: además de ver, puede editar todo.<br>"
                "• <b>ver_todos_los_pagos</b>: ignora el recorte por años y muestra todos los pagos."
            )
        }),
    )

    @admin.display(description="Sedes")
    def sedes_list(self, obj):
        return ", ".join(obj.sedes.values_list("nombre", flat=True))


# --------- Inline del perfil en el admin de Usuario ---------
User = get_user_model()

class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    fk_name = "user"
    filter_horizontal = ("sedes",)
    extra = 0

    fieldsets = (
        (None, {
            "fields": ("sedes",),
        }),
        ("Permisos", {
            "fields": ("puede_ver_todo", "puede_editar_todo", "ver_todos_los_pagos"),
        }),
    )

# Si el User ya está registrado por otra app, lo reemplazamos para añadir el inline
try:
    admin.site.unregister(User)
except admin.sites.NotRegistered:
    pass

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    inlines = [UserProfileInline]

######################################################################################
# admin.py


from django.db.models import F
from .models import ContadorAlumno

@admin.register(ContadorAlumno)
class ContadorAlumnoAdmin(admin.ModelAdmin):
    list_display = ("llave", "ultimo_numero", "siguiente_numero")    
    search_fields = ("llave",)
    list_per_page = 25

    # Solo lectura del ID por comodidad (si lo muestras en el form)
    readonly_fields = ()

    fieldsets = (
        (None, {
            "fields": ("llave", "ultimo_numero"),
            "description": "Contador por llave. Usa las acciones para incrementar o resetear de forma segura."
        }),
    )

    def siguiente_numero(self, obj):
        return obj.ultimo_numero + 1
    siguiente_numero.short_description = "Siguiente"

    # ========== ACCIONES ==========
    actions = ["incrementar_1", "incrementar_10", "resetear_a_cero"]

    @admin.action(description="Incrementar +1 (atómico)")
    def incrementar_1(self, request, queryset):
        self._incrementar(request, queryset, step=1)

    @admin.action(description="Incrementar +10 (atómico)")
    def incrementar_10(self, request, queryset):
        self._incrementar(request, queryset, step=10)

    @admin.action(description="Resetear a 0 (atómico)")
    def resetear_a_cero(self, request, queryset):
        with transaction.atomic():
            updated = queryset.update(ultimo_numero=0)
        self.message_user(request, f"Se reseteó a 0 en {updated} contador(es).", level=messages.SUCCESS)

    # Helper para incremento seguro
    def _incrementar(self, request, queryset, step):
        with transaction.atomic():
            updated = 0
            # Usamos F() para evitar condiciones de carrera
            for obj in queryset:
                ContadorAlumno.objects.filter(pk=obj.pk).update(ultimo_numero=F("ultimo_numero") + step)
                updated += 1
        self.message_user(request, f"Incrementados +{step} en {updated} contador(es).", level=messages.SUCCESS)


from .models import ClipCredential
@admin.register(ClipCredential)
class ClipCredentialAdmin(admin.ModelAdmin):
    list_display = ("name", "is_sandbox", "active", "updated_at")
    list_filter = ("is_sandbox", "active")
    search_fields = ("name", "public_key")
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        (None, {
            "fields": ("name", "public_key", "secret_key", "is_sandbox", "active")
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at"),
        }),
    )

from .models import ClipPaymentOrder
@admin.register(ClipPaymentOrder)
class ClipPaymentOrderAdmin(admin.ModelAdmin):
    list_display = ("id", "alumno", "cargo", "amount", "currency", "status", "clip_payment_id", "created_at")
    list_filter  = ("status", "currency",)
    search_fields = ("id", "clip_payment_id", "description")
    readonly_fields = ("created_at", "updated_at", "raw_request", "raw_response", "last_webhook")    