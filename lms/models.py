from django.db import models
from alumnos.models import Alumno, Programa, Grupo

class Curso(models.Model):
    programa = models.ForeignKey(
        Programa, on_delete=models.CASCADE, related_name="cursos_lms"
    )
    grupo = models.ForeignKey(
        Grupo, on_delete=models.SET_NULL, null=True, blank=True, related_name="cursos_lms"
    )
    nombre = models.CharField(max_length=255)
    codigo = models.CharField(max_length=50, unique=True)
    descripcion = models.TextField(blank=True)
    docente = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cursos_docente"
    )

    # 🔹 NUEVO: imagen / portada del curso
    portada = models.ImageField(
        "Imagen del curso",
        upload_to="lms/cursos_portadas/",
        null=True,
        blank=True,
    )

     # 🔹 NUEVOS CAMPOS
    fecha_inicio = models.DateField(
        "Fecha de inicio",
        null=True,
        blank=True,
    )
    fecha_fin = models.DateField(
        "Fecha de finalización",
        null=True,
        blank=True,
    )

    activo = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.codigo} - {self.nombre}"


class Modulo(models.Model):
    curso = models.ForeignKey(Curso, on_delete=models.CASCADE, related_name="modulos")
    titulo = models.CharField(max_length=255)
    orden = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["orden"]

    def __str__(self):
        return f"{self.curso.codigo} - {self.titulo}"


class Leccion(models.Model):
    modulo = models.ForeignKey(Modulo, on_delete=models.CASCADE, related_name="lecciones")
    titulo = models.CharField(max_length=255)
    contenido_html = models.TextField(blank=True)  # aquí puedes meter texto enriquecido
    archivo = models.FileField(upload_to="lms/lecciones/", blank=True, null=True)
    url_video = models.URLField(blank=True)
    embed_video = models.TextField(blank=True)  # 👈 nuevo campo para el iframe

    orden = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["orden"]

    def __str__(self):
        return self.titulo


class Actividad(models.Model):
    TIPO_CHOICES = (
        ("tarea", "Tarea"),
        ("quiz", "Cuestionario"),
        ("foro", "Foro"),
    )

    leccion = models.ForeignKey(Leccion, on_delete=models.CASCADE, related_name="actividades")
    titulo = models.CharField(max_length=255)
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, default="tarea")
    instrucciones = models.TextField(blank=True)
    fecha_inicio = models.DateTimeField(null=True, blank=True)
    fecha_limite = models.DateTimeField(null=True, blank=True)
    calificacion_maxima = models.DecimalField(max_digits=5, decimal_places=2, default=10)

    def __str__(self):
        return self.titulo


class Entrega(models.Model):
    actividad = models.ForeignKey(Actividad, on_delete=models.CASCADE, related_name="entregas")
    alumno = models.ForeignKey(Alumno, on_delete=models.CASCADE, related_name="entregas_lms")
    archivo = models.FileField(upload_to="lms/entregas/", blank=True, null=True)
    texto_respuesta = models.TextField(blank=True)
    enviado_en = models.DateTimeField(auto_now_add=True)
    calificacion = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    retroalimentacion_docente = models.TextField(blank=True)
    calificado_en = models.DateTimeField(null=True, blank=True)
    calificado_por = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="entregas_calificadas"
    )

    class Meta:
        unique_together = ("actividad", "alumno")

    def __str__(self):
        return f"{self.actividad} - {self.alumno}"


class AccesoCurso(models.Model):
    alumno = models.ForeignKey(Alumno, on_delete=models.CASCADE, related_name="accesos_lms")
    curso = models.ForeignKey(Curso, on_delete=models.CASCADE, related_name="accesos")
    ultimo_acceso = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("alumno", "curso")


class AlertaAcademica(models.Model):
    alumno = models.ForeignKey(Alumno, on_delete=models.CASCADE, related_name="alertas_academicas")
    curso = models.ForeignKey(Curso, on_delete=models.CASCADE, null=True, blank=True)
    mensaje = models.TextField()
    creada_en = models.DateTimeField(auto_now_add=True)
    atendida = models.BooleanField(default=False)
#################################################################################
class Pregunta(models.Model):
    TIPO_CHOICES = (
        ("opcion_multiple", "Opción múltiple"),
        ("abierta", "Respuesta abierta"),
    )

    actividad = models.ForeignKey(
        Actividad,
        on_delete=models.CASCADE,
        related_name="preguntas",
    )
    texto = models.TextField()
    tipo = models.CharField(
        max_length=20,
        choices=TIPO_CHOICES,
        default="opcion_multiple",
    )
    orden = models.PositiveIntegerField(default=1)
    puntaje = models.DecimalField(max_digits=5, decimal_places=2, default=1)

    class Meta:
        ordering = ["orden"]

    def __str__(self):
        return f"{self.actividad.titulo} - {self.orden}. {self.texto[:50]}..."


class OpcionPregunta(models.Model):
    pregunta = models.ForeignKey(
        Pregunta,
        on_delete=models.CASCADE,
        related_name="opciones",
    )
    texto = models.CharField(max_length=255)
    es_correcta = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.pregunta.id} - {self.texto[:50]}{' (✓)' if self.es_correcta else ''}"


class IntentoQuiz(models.Model):
    """
    Un intento de un alumno para una Actividad tipo QUIZ.
    """
    actividad = models.ForeignKey(
        Actividad,
        on_delete=models.CASCADE,
        related_name="intentos",
    )
    alumno = models.ForeignKey(
        Alumno,
        on_delete=models.CASCADE,
        related_name="intentos_quiz",
    )
    iniciado_en = models.DateTimeField(auto_now_add=True)
    completado_en = models.DateTimeField(null=True, blank=True)
    calificacion_obtenida = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
    )

    class Meta:
        unique_together = ("actividad", "alumno")  # un intento por ahora

    def __str__(self):
        return f"Quiz {self.actividad_id} - {self.alumno} ({self.calificacion_obtenida})"


class RespuestaPregunta(models.Model):
    intento = models.ForeignKey(
        IntentoQuiz,
        on_delete=models.CASCADE,
        related_name="respuestas",
    )
    pregunta = models.ForeignKey(
        Pregunta,
        on_delete=models.CASCADE,
        related_name="respuestas",
    )
    opcion = models.ForeignKey(
        OpcionPregunta,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="respuestas",
    )
    texto_respuesta = models.TextField(blank=True)

    def __str__(self):
        return f"Resp {self.pregunta_id} - intento {self.intento_id}"
