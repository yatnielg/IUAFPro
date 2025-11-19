# lms/admin.py
from django.contrib import admin

from .models import (
    Curso,
    Modulo,
    Leccion,
    Actividad,
    Entrega,
    AccesoCurso,
    AlertaAcademica,
    Pregunta,
    OpcionPregunta,
    IntentoQuiz,
    RespuestaPregunta,
)

# ==========================
# INLINES
# ==========================

class ModuloInline(admin.TabularInline):
    model = Modulo
    extra = 1
    fields = ("titulo", "orden")
    ordering = ("orden",)


class LeccionInline(admin.TabularInline):
    model = Leccion
    extra = 1
    fields = ("titulo", "orden", "archivo", "url_video")
    ordering = ("orden",)


class ActividadInline(admin.TabularInline):
    model = Actividad
    extra = 1
    fields = ("titulo", "tipo", "fecha_inicio", "fecha_limite", "calificacion_maxima")
    ordering = ("fecha_inicio",)


class PreguntaInline(admin.TabularInline):
    model = Pregunta
    extra = 1
    fields = ("texto", "tipo", "orden", "puntaje")
    ordering = ("orden",)
    show_change_link = True


class OpcionPreguntaInline(admin.TabularInline):
    model = OpcionPregunta
    extra = 2
    fields = ("texto", "es_correcta")


class RespuestaPreguntaInline(admin.TabularInline):
    model = RespuestaPregunta
    extra = 0
    fields = ("pregunta", "opcion", "texto_respuesta")
    readonly_fields = ("pregunta", "opcion", "texto_respuesta")


# ==========================
# CURSO / MÓDULO / LECCIÓN / ACTIVIDAD
# ==========================

@admin.register(Curso)
class CursoAdmin(admin.ModelAdmin):
    list_display = ("codigo", "nombre", "programa", "grupo", "docente", "activo")
    list_filter = ("activo", "programa", "grupo")
    search_fields = ("codigo", "nombre", "descripcion", "programa__nombre")
    inlines = [ModuloInline]
    autocomplete_fields = ("programa", "grupo", "docente")
    list_per_page = 25


@admin.register(Modulo)
class ModuloAdmin(admin.ModelAdmin):
    list_display = ("titulo", "curso", "orden")
    list_filter = ("curso",)
    search_fields = ("titulo", "curso__nombre", "curso__codigo")
    ordering = ("curso", "orden")
    inlines = [LeccionInline]
    autocomplete_fields = ("curso",)
    list_per_page = 25


@admin.register(Leccion)
class LeccionAdmin(admin.ModelAdmin):
    list_display = ("titulo", "modulo", "curso_nombre", "orden")
    list_filter = ("modulo__curso",)
    search_fields = ("titulo", "modulo__curso__nombre", "modulo__curso__codigo")
    ordering = ("modulo__curso", "modulo", "orden")
    inlines = [ActividadInline]
    autocomplete_fields = ("modulo",)
    list_per_page = 25

    @admin.display(description="Curso")
    def curso_nombre(self, obj):
        return obj.modulo.curso if obj.modulo else None


@admin.register(Actividad)
class ActividadAdmin(admin.ModelAdmin):
    list_display = (
        "titulo",
        "tipo",
        "leccion",
        "curso",
        "fecha_inicio",
        "fecha_limite",
        "calificacion_maxima",
    )
    list_filter = ("tipo", "leccion__modulo__curso")
    search_fields = (
        "titulo",
        "instrucciones",
        "leccion__titulo",
        "leccion__modulo__curso__nombre",
    )
    ordering = ("leccion__modulo__curso", "leccion__modulo", "leccion", "fecha_inicio")
    inlines = [PreguntaInline]
    autocomplete_fields = ("leccion",)
    list_per_page = 25

    @admin.display(description="Curso")
    def curso(self, obj):
        if obj.leccion and obj.leccion.modulo:
            return obj.leccion.modulo.curso
        return None


# ==========================
# ENTREGAS / ACCESOS / ALERTAS
# ==========================

@admin.register(Entrega)
class EntregaAdmin(admin.ModelAdmin):
    list_display = (
        "actividad",
        "alumno",
        "enviado_en",
        "calificacion",
        "calificado_por",
    )
    list_filter = ("actividad", "calificado_por")
    search_fields = (
        "actividad__titulo",
        "alumno__nombre",
        "alumno__apellido_p",
        "alumno__apellido_m",
    )
    autocomplete_fields = ("actividad", "alumno", "calificado_por")
    date_hierarchy = "enviado_en"
    list_per_page = 25


@admin.register(AccesoCurso)
class AccesoCursoAdmin(admin.ModelAdmin):
    list_display = ("alumno", "curso", "ultimo_acceso")
    list_filter = ("curso",)
    search_fields = (
        "alumno__nombre",
        "alumno__apellido_p",
        "alumno__apellido_m",
        "curso__nombre",
        "curso__codigo",
    )
    autocomplete_fields = ("alumno", "curso")
    date_hierarchy = "ultimo_acceso"
    list_per_page = 25


@admin.register(AlertaAcademica)
class AlertaAcademicaAdmin(admin.ModelAdmin):
    list_display = ("alumno", "curso", "mensaje_corto", "creada_en", "atendida")
    list_filter = ("atendida", "curso")
    search_fields = (
        "mensaje",
        "alumno__nombre",
        "alumno__apellido_p",
        "alumno__apellido_m",
        "curso__nombre",
        "curso__codigo",
    )
    autocomplete_fields = ("alumno", "curso")
    date_hierarchy = "creada_en"
    list_per_page = 25

    @admin.display(description="Mensaje")
    def mensaje_corto(self, obj):
        return (obj.mensaje[:60] + "...") if len(obj.mensaje) > 60 else obj.mensaje


# ==========================
# PREGUNTAS / OPCIONES / QUIZ
# ==========================

@admin.register(Pregunta)
class PreguntaAdmin(admin.ModelAdmin):
    list_display = ("texto_corto", "actividad", "tipo", "orden", "puntaje")
    list_filter = ("tipo", "actividad__leccion__modulo__curso")
    search_fields = ("texto", "actividad__titulo")
    ordering = ("actividad", "orden")
    inlines = [OpcionPreguntaInline]
    autocomplete_fields = ("actividad",)
    list_per_page = 25

    @admin.display(description="Pregunta")
    def texto_corto(self, obj):
        return (obj.texto[:60] + "...") if len(obj.texto) > 60 else obj.texto


@admin.register(OpcionPregunta)
class OpcionPreguntaAdmin(admin.ModelAdmin):
    list_display = ("texto_corto", "pregunta", "es_correcta")
    list_filter = ("es_correcta", "pregunta__actividad__leccion__modulo__curso")
    search_fields = ("texto", "pregunta__texto", "pregunta__actividad__titulo")
    autocomplete_fields = ("pregunta",)
    list_per_page = 25

    @admin.display(description="Opción")
    def texto_corto(self, obj):
        return (obj.texto[:60] + "...") if len(obj.texto) > 60 else obj.texto


@admin.register(IntentoQuiz)
class IntentoQuizAdmin(admin.ModelAdmin):
    list_display = (
        "actividad",
        "alumno",
        "calificacion_obtenida",
        "iniciado_en",
        "completado_en",
    )
    list_filter = ("actividad",)
    search_fields = (
        "actividad__titulo",
        "alumno__nombre",
        "alumno__apellido_p",
        "alumno__apellido_m",
    )
    autocomplete_fields = ("actividad", "alumno")
    date_hierarchy = "iniciado_en"
    inlines = [RespuestaPreguntaInline]
    list_per_page = 25


@admin.register(RespuestaPregunta)
class RespuestaPreguntaAdmin(admin.ModelAdmin):
    list_display = ("intento", "pregunta", "opcion", "texto_corto")
    list_filter = ("pregunta__actividad",)
    search_fields = (
        "texto_respuesta",
        "pregunta__texto",
        "intento__alumno__nombre",
        "intento__alumno__apellido_p",
        "intento__alumno__apellido_m",
    )
    autocomplete_fields = ("intento", "pregunta", "opcion")
    list_per_page = 25

    @admin.display(description="Respuesta")
    def texto_corto(self, obj):
        if not obj.texto_respuesta:
            return ""
        return (
            obj.texto_respuesta[:60] + "..."
            if len(obj.texto_respuesta) > 60
            else obj.texto_respuesta
        )
