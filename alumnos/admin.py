from django.contrib import admin
from .models import Alumno, ConceptoPago, Cargo, Pago, Pais, Estado
from .models import Programa

class EstadoInline(admin.TabularInline):
    model = Estado
    extra = 1

@admin.register(Pais)
class PaisAdmin(admin.ModelAdmin):
    list_display = ("nombre", "codigo_iso2", "codigo_iso3", "requiere_estado")
    list_filter = ("requiere_estado",)
    search_fields = ("nombre", "codigo_iso2", "codigo_iso3")
    inlines = [EstadoInline]

@admin.register(Estado)
class EstadoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "pais")
    list_filter = ("pais",)
    search_fields = ("nombre", "pais__nombre")

@admin.register(Alumno)
class AlumnoAdmin(admin.ModelAdmin):
    list_display = ("numero_estudiante", "nombre", "apellido_p", "pais", "estado", "programa", "estatus")
    list_filter = ("pais", "estado", "programa", "estatus", "estatus_academico", "estatus_administrativo")
    search_fields = ("numero_estudiante", "nombre", "apellido_p", "apellido_m", "email", "curp")

@admin.register(Programa)
class ProgramaAdmin(admin.ModelAdmin):
    list_display = ("codigo", "nombre", "meses_programa", "colegiatura", "inscripcion", "reinscripcion", "equivalencia", "titulacion", "activo")
    search_fields = ("codigo", "nombre")
    list_filter = ("activo",)