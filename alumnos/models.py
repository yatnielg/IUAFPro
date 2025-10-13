from django.db import models
from django.core.exceptions import ValidationError
from django.conf import settings

from decimal import Decimal
from django.core.validators import MinValueValidator

# Create your models here.
class Pais(models.Model):
    nombre = models.CharField(max_length=120, unique=True)
    codigo_iso2 = models.CharField("Código ISO-2", max_length=2, blank=True)   # ej. MX, US
    codigo_iso3 = models.CharField("Código ISO-3", max_length=3, blank=True)   # ej. MEX, USA
    requiere_estado = models.BooleanField(
        "¿Requiere estado/provincia?",
        default=False,
        help_text="Si es verdadero, el alumno debe seleccionar un estado/provincia."
    )
    class Meta:
            verbose_name = "País"
            verbose_name_plural = "Países"
            ordering = ["nombre"]
            indexes = [
                models.Index(fields=["nombre"]),
                models.Index(fields=["codigo_iso2"]),
                models.Index(fields=["codigo_iso3"]),
            ]

    def __str__(self):
            return f"{self.nombre}"
            
class Estado(models.Model):
    pais = models.ForeignKey(Pais, on_delete=models.CASCADE, related_name="estados")
    nombre = models.CharField(max_length=120)

    class Meta:
        verbose_name = "Estado/Provincia"
        verbose_name_plural = "Estados/Provincias"
        ordering = ["pais__nombre", "nombre"]
        unique_together = [("pais", "nombre")]
        indexes = [
            models.Index(fields=["pais", "nombre"]),
        ]

    def __str__(self):
        return f"{self.nombre} ({self.pais.nombre})"
    
############################################################################
class Programa(models.Model):
    codigo = models.CharField("Programas (código)", max_length=20, unique=True)  # ej. LD, MD, DD, DIAP, JTLD...
    nombre = models.CharField("Nombre de Cursos", max_length=200)               # ej. LICENCIATURA EN DERECHO
    meses_programa = models.PositiveIntegerField("Meses Programa", validators=[MinValueValidator(1)])

    colegiatura = models.DecimalField("Colegiatura", max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0"))])
    inscripcion = models.DecimalField("Inscripción", max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0"))])
    reinscripcion = models.DecimalField("Reinscripción", max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0"))])
    equivalencia = models.DecimalField("Equivalencia", max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0"))])
    titulacion = models.DecimalField("Titulación", max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0"))])

    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Programa"
        verbose_name_plural = "Programas"
        ordering = ["nombre"]
        indexes = [
            models.Index(fields=["codigo"]),
            models.Index(fields=["nombre"]),
            models.Index(fields=["activo"]),
        ]

    def __str__(self):
        return f"{self.codigo} — {self.nombre}"
    
    @property
    def nombre_ayuda(self):
        return self.nombre

############################################################################
class Alumno(models.Model):
    SEXO_OPCIONES = [
        ("Hombre", "Hombre"),
        ("Mujer", "Mujer"),
    ]
    # ID oficial: número de estudiante tal cual en Excel
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="perfil_alumno"
    )
    numero_estudiante = models.CharField(
        "Número de estudiante",
        max_length=32,
        primary_key=True
    )
    curp = models.CharField("CURP", max_length=18, unique=True, null=True, blank=True)

    # NUEVOS CAMPOS
    pais = models.ForeignKey(Pais, on_delete=models.PROTECT, null=True, blank=True, related_name="alumnos")
    estado = models.ForeignKey(Estado, on_delete=models.PROTECT, null=True, blank=True, related_name="alumnos")


    estatus_academico = models.CharField("Estatus académico", max_length=60, blank=True)
    estatus_administrativo = models.CharField("Estatus administrativo", max_length=60, blank=True)
    nombre = models.CharField('Nombre(s)',max_length=120)
    apellido_p = models.CharField("Apellido paterno", max_length=120, blank=True)
    apellido_m = models.CharField("Apellido materno", max_length=120, blank=True)
    email = models.EmailField(blank=True)
    telefono = models.CharField(max_length=40, blank=True)
    programa = models.ForeignKey(
        "Programa", on_delete=models.PROTECT, null=True, blank=True, related_name="alumnos", verbose_name="Programa"
    )
    estatus = models.CharField(max_length=60, blank=True)
    fecha_nacimiento = models.DateField(null=True, blank=True)
    fecha_alta = models.DateTimeField(auto_now_add=True)
    sexo = models.CharField(
        "Sexo",
        max_length=20,
        choices=SEXO_OPCIONES,
        blank=True
    )

    class Meta:
        ordering = ["apellido_p", "apellido_m", "nombre"]
        indexes = [
            models.Index(fields=["numero_estudiante"]),
            models.Index(fields=["curp"]),
            models.Index(fields=["apellido_p", "apellido_m"]),
            models.Index(fields=["pais"]),
            models.Index(fields=["estado"]),
        ]


    @property
    def programa_clave(self):
        # devuelve lo anterior a "—"
        return self.programa.codigo

    def clean(self):
        # Si el país requiere estado, validar que estado esté presente y pertenezca a ese país
        if self.pais and self.pais.requiere_estado:
            if not self.estado:
                raise ValidationError({"estado": "Este país requiere seleccionar un estado/provincia."})
            if self.estado and self.estado.pais_id != self.pais_id:
                raise ValidationError({"estado": "El estado seleccionado no pertenece al país indicado."})
        # Si el país NO requiere estado, limpiamos estado para evitar inconsistencias
        if self.pais and not self.pais.requiere_estado and self.estado:
            self.estado = None

    def __str__(self):
        return f"{self.numero_estudiante} - {self.nombre} {self.apellido_p}".strip()

############################################################################
class ConceptoPago(models.Model):
    codigo = models.CharField(max_length=40, unique=True)
    nombre = models.CharField(max_length=120)
    recurrente = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.codigo} - {self.nombre}"


class Cargo(models.Model):
    alumno = models.ForeignKey(Alumno, on_delete=models.CASCADE, related_name="cargos")
    concepto = models.ForeignKey(ConceptoPago, on_delete=models.PROTECT)
    monto = models.DecimalField(max_digits=12, decimal_places=2)
    fecha_cargo = models.DateField()
    fecha_vencimiento = models.DateField(null=True, blank=True)
    folio = models.CharField(max_length=50, blank=True)
    pagado = models.BooleanField(default=False)

    def __str__(self):
        return f"Cargo {self.id} - {self.alumno_id} - {self.concepto.codigo}"


class Pago(models.Model):
    alumno = models.ForeignKey(Alumno, on_delete=models.SET_NULL, null=True, related_name="pagos")
    fecha = models.DateField()
    monto = models.DecimalField(max_digits=12, decimal_places=2)
    metodo = models.CharField(max_length=40, blank=True)       # Transferencia, Efectivo…
    banco = models.CharField(max_length=60, blank=True)
    referencia = models.CharField(max_length=80, blank=True)
    descripcion = models.TextField(blank=True)
    conciliado = models.BooleanField(default=False)
    cargo = models.ForeignKey(Cargo, null=True, blank=True, on_delete=models.SET_NULL, related_name="pagos")

    def __str__(self):
        return f"Pago {self.id} - {self.alumno_id or 'SIN ALUMNO'} - {self.monto}"
    
