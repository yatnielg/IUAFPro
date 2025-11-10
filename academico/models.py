# academico/models.py
from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone

from alumnos.models import Programa, Alumno  # ya los tienes

class Materia(models.Model):
    """
    Catálogo de materias (única vez por materia). 
    Si ya tienes un catálogo, podemos apuntar a ese.
    """
    codigo = models.CharField(max_length=32, unique=True)
    nombre = models.CharField(max_length=255)

    class Meta:
        ordering = ["codigo"]

    def __str__(self):
        return f"{self.codigo} — {self.nombre}"


class ListadoMaterias(models.Model):
    """
    Un 'listado' (p. ej. Plan 2025-A, Trimestre 1, Cohorte X) pertenece a un Programa
    y agrupa varias Materias (cada una con fechas).
    """
    programa = models.ForeignKey(Programa, on_delete=models.CASCADE, related_name="listados")
    nombre = models.CharField(max_length=150)  # ej. "Plan Ene–Abr 2026"
    descripcion = models.TextField(blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("programa", "nombre")]
        ordering = ["-creado_en"]

    def __str__(self):
        return f"{self.programa.codigo} · {self.nombre}"


class ListadoMateriaItem(models.Model):
    """
    Una materia dentro de un listado, con su ventana temporal.
    """
    listado = models.ForeignKey(ListadoMaterias, on_delete=models.CASCADE, related_name="items")
    materia = models.ForeignKey(Materia, on_delete=models.PROTECT, related_name="ofertas")
    fecha_inicio = models.DateField(null=True, blank=True)
    fecha_fin = models.DateField(null=True, blank=True)

    class Meta:
        unique_together = [("listado", "materia")]
        ordering = ["fecha_inicio", "materia__codigo"]

    def __str__(self):
        return f"{self.listado} · {self.materia}"

    def clean(self):
        if self.fecha_inicio and self.fecha_fin and self.fecha_fin < self.fecha_inicio:
            raise ValidationError("La fecha de fin no puede ser menor a la de inicio.")


class ListadoAlumno(models.Model):
    """
    Relación de alumnos asignados a un listado. 
    Validamos que el alumno pertenezca al MISMO programa del listado.
    """
    listado = models.ForeignKey(ListadoMaterias, on_delete=models.CASCADE, related_name="inscripciones")
    alumno = models.ForeignKey(Alumno, on_delete=models.CASCADE, related_name="listados")
    agregado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("listado", "alumno")]
        ordering = ["-agregado_en"]

    def __str__(self):
        return f"{self.listado} · {self.alumno.numero_estudiante}"

    def clean(self):
        info = getattr(self.alumno, "informacionEscolar", None)
        if not info or not info.programa_id:
            raise ValidationError("El alumno no tiene programa asignado.")
        if info.programa_id != self.listado.programa_id:
            raise ValidationError("El alumno debe pertenecer al mismo programa del listado.")

class Calificacion(models.Model):
    """
    Nota del alumno en una materia específica dentro de un Listado.
    item -> referencia a la Materia en el Listado (con fechas)
    alumno -> debe estar inscrito en el mismo Listado (ListadoAlumno)
    """
    item = models.ForeignKey(ListadoMateriaItem, on_delete=models.CASCADE, related_name="calificaciones")
    alumno = models.ForeignKey(Alumno, on_delete=models.CASCADE, related_name="calificaciones_materia")

    # Nota en escala 0-100 (ajusta si usas otra)
    nota = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    aprobado = models.BooleanField(default=False)
    observaciones = models.TextField(blank=True)

    capturado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("item", "alumno")]
        indexes = [
            models.Index(fields=["item", "alumno"]),
        ]
        ordering = ["item__fecha_inicio", "alumno__numero_estudiante"]

    def __str__(self):
        return f"{self.item.listado.programa.codigo} · {self.item.materia.codigo} · {self.alumno.numero_estudiante} · {self.nota or '—'}"

    def clean(self):
        # Validar pertenencia al mismo programa del listado
        info = getattr(self.alumno, "informacionEscolar", None)
        if not info or not info.programa_id:
            raise ValidationError("El alumno no tiene programa asignado.")
        if info.programa_id != self.item.listado.programa_id:
            raise ValidationError("El alumno debe pertenecer al mismo programa del listado de la materia.")

        # Validar rango de nota si viene
        if self.nota is not None:
            try:
                v = float(self.nota)
            except Exception:
                raise ValidationError("La nota debe ser numérica.")
            if v < 0 or v > 100:
                raise ValidationError("La nota debe estar entre 0 y 100.")

    def save(self, *args, **kwargs):
        # si hay nota, marca aprobado según umbral (ajusta umbral si es diferente)
        if self.nota is not None:
            self.aprobado = float(self.nota) >= 60.0
        super().save(*args, **kwargs)
