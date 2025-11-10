# academico/admin.py
from django.contrib import admin
from django.db import models
from django.db.models import Q

from alumnos.models import Alumno
from .models import (
    Materia,
    ListadoMaterias,
    ListadoMateriaItem,
    ListadoAlumno,
    Calificacion,   # <-- importa Calificacion
)

# -----------------------------
#  Materia
# -----------------------------
@admin.register(Materia)
class MateriaAdmin(admin.ModelAdmin):
    list_display = ("codigo", "nombre")
    search_fields = ("codigo", "nombre")
    ordering = ("codigo",)


# -----------------------------
#  Inlines para ListadoMaterias
# -----------------------------
class ListadoMateriaItemInline(admin.TabularInline):
    model = ListadoMateriaItem
    extra = 1
    autocomplete_fields = ("materia",)
    fields = ("materia", "fecha_inicio", "fecha_fin")
    ordering = ("fecha_inicio", "materia__codigo")


class ListadoAlumnoInline(admin.TabularInline):
    """
    Inscripción de alumnos al listado. Filtra alumnos al mismo programa del Listado.
    """
    model = ListadoAlumno
    extra = 1
    autocomplete_fields = ("alumno",)
    fields = ("alumno", "agregado_en")
    readonly_fields = ("agregado_en",)
    ordering = ("-agregado_en",)

    def get_formset(self, request, obj=None, **kwargs):
        """
        Al tener `obj` (ListadoMaterias) limitamos los alumnos al mismo programa.
        """
        FormSet = super().get_formset(request, obj, **kwargs)
        if obj:
            base_qs = Alumno.objects.select_related("informacionEscolar", "informacionEscolar__programa")
            FormSet.form.base_fields["alumno"].queryset = base_qs.filter(
                informacionEscolar__programa=obj.programa
            )
        return FormSet


# -----------------------------
#  ListadoMaterias (padre)
# -----------------------------
@admin.register(ListadoMaterias)
class ListadoMateriasAdmin(admin.ModelAdmin):
    list_display = ("nombre", "programa", "items_count", "inscritos_count", "creado_en")
    list_filter  = ("programa",)
    search_fields = ("nombre", "programa__codigo", "programa__nombre")
    date_hierarchy = "creado_en"
    ordering = ("-creado_en",)
    inlines = [ListadoMateriaItemInline, ListadoAlumnoInline]
    readonly_fields = ("creado_en",)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(
            _items_count=models.Count("items", distinct=True),
            _inscritos_count=models.Count("inscripciones", distinct=True),
        )

    def items_count(self, obj):
        return getattr(obj, "_items_count", obj.items.count())
    items_count.short_description = "Materias"

    def inscritos_count(self, obj):
        return getattr(obj, "_inscritos_count", obj.inscripciones.count())
    inscritos_count.short_description = "Alumnos"


# -----------------------------
#  Inline de Calificaciones por materia del listado
# -----------------------------
class CalificacionInline(admin.TabularInline):
    model = Calificacion
    extra = 0
    autocomplete_fields = ("alumno",)
    fields = ("alumno", "nota", "aprobado", "observaciones", "capturado_en", "actualizado_en")
    readonly_fields = ("aprobado", "capturado_en", "actualizado_en")
    ordering = ("alumno__numero_estudiante",)

    def get_formset(self, request, obj=None, **kwargs):
        """
        Limita el FK 'alumno' a los alumnos inscritos en el mismo listado del item.
        Aquí `obj` es un ListadoMateriaItem.
        """
        FormSet = super().get_formset(request, obj, **kwargs)
        if obj:
            listado = obj.listado
            inscripciones = ListadoAlumno.objects.filter(listado=listado).only("alumno_id")
            alumnos_ids = [ins.alumno_id for ins in inscripciones]
            base_qs = Alumno.objects.select_related("informacionEscolar", "informacionEscolar__programa")
            FormSet.form.base_fields["alumno"].queryset = base_qs.filter(pk__in=alumnos_ids)
        return FormSet


# -----------------------------
#  ListadoMateriaItem (único registro)
# -----------------------------
@admin.register(ListadoMateriaItem)
class ListadoMateriaItemAdmin(admin.ModelAdmin):
    list_display = ("listado", "materia", "fecha_inicio", "fecha_fin")
    list_filter = ("listado__programa", "listado",)
    search_fields = ("listado__nombre", "materia__codigo", "materia__nombre")
    autocomplete_fields = ("listado", "materia")
    ordering = ("listado", "fecha_inicio", "materia__codigo")
    inlines = [CalificacionInline]


# -----------------------------
#  ListadoAlumno (opcional)
# -----------------------------
@admin.register(ListadoAlumno)
class ListadoAlumnoAdmin(admin.ModelAdmin):
    list_display = ("listado", "alumno", "programa_del_listado", "programa_del_alumno", "agregado_en")
    list_filter = ("listado__programa", "listado",)
    search_fields = (
        "listado__nombre",
        "alumno__numero_estudiante",
        "alumno__nombre",
        "alumno__apellido_p",
        "alumno__apellido_m",
    )
    autocomplete_fields = ("listado", "alumno")
    date_hierarchy = "agregado_en"
    ordering = ("-agregado_en",)

    def programa_del_listado(self, obj):
        return obj.listado.programa
    programa_del_listado.short_description = "Programa (Listado)"

    def programa_del_alumno(self, obj):
        info = getattr(obj.alumno, "informacionEscolar", None)
        return getattr(info, "programa", None)
    programa_del_alumno.short_description = "Programa (Alumno)"

    # academico/admin.py (extra)
from .models import Calificacion

@admin.register(Calificacion)
class CalificacionAdmin(admin.ModelAdmin):
    list_display = ("item", "alumno", "nota", "aprobado", "capturado_en")
    list_filter  = ("item__listado__programa", "item__listado", "aprobado")
    search_fields = (
        "item__materia__codigo", "item__materia__nombre",
        "item__listado__nombre",
        "alumno__numero_estudiante", "alumno__nombre", "alumno__apellido_p", "alumno__apellido_m",
    )
    autocomplete_fields = ("item", "alumno")
    ordering = ("-capturado_en",)

