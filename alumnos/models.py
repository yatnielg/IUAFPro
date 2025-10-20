from django.db import models
from django.core.exceptions import ValidationError
from django.conf import settings

from decimal import Decimal
from django.core.validators import MinValueValidator
from django.utils import timezone

# Create your models here.
class UserProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    sedes = models.ManyToManyField("Sede", blank=True)  # sedes a las que el usuario está asignado

    # flags de alcance global
    puede_ver_todo = models.BooleanField(default=False)
    puede_editar_todo = models.BooleanField(default=False)  # si esto es True, ya implica ver_todo
    # ver todos los pagos (ignora el recorte a 2 años)
    ver_todos_los_pagos = models.BooleanField(default=False,help_text="Si está activo, el usuario verá todos los pagos (sin límite de años).")

    def __str__(self):
        return f"Perfil de {self.user}"
####################################################################################################
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models

class Financiamiento(models.Model):
    TIPO_DESCUENTO = [
        ("ninguno", "Sin descuento"),
        ("porcentaje", "Porcentaje"),
        ("monto", "Monto fijo"),
    ]

    beca = models.CharField(
        "Beca",
        max_length=120,
        blank=True,
        help_text="Ej.: Beca Académica, Beca 50%, Convenio, etc."
    )
    tipo_descuento = models.CharField(
        "Tipo de descuento",
        max_length=20,
        choices=TIPO_DESCUENTO,
        default="ninguno",
        help_text="Selecciona si el descuento es porcentual o de monto fijo."
    )
    porcentaje_descuento = models.DecimalField(
        "Porcentaje de descuento",
        max_digits=5, decimal_places=2,
        null=True, blank=True,
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
        help_text="Solo si el tipo es 'Porcentaje'. Ej.: 15.5 = 15.5%."
    )
    monto_descuento = models.DecimalField(
        "Monto fijo a descontar",
        max_digits=12, decimal_places=2,
        null=True, blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Solo si el tipo es 'Monto fijo'. Ej.: 1500.00"
    )

    class Meta:
        verbose_name = "Financiamiento"
        verbose_name_plural = "Financiamientos"
        ordering = ["id"]

    def __str__(self):
        if self.tipo_descuento == "porcentaje" and self.porcentaje_descuento is not None:
            return f"{self.beca or 'Sin nombre'} — {self.porcentaje_descuento}%"
        if self.tipo_descuento == "monto" and self.monto_descuento is not None:
            return f"{self.beca or 'Sin nombre'} — ${self.monto_descuento}"
        return self.beca or "Sin nombre"

    def clean(self):
        """
        Valida coherencia entre tipo_descuento y los campos de valor.
        """
        from django.core.exceptions import ValidationError

        if self.tipo_descuento == "porcentaje":
            if self.porcentaje_descuento is None:
                raise ValidationError({"porcentaje_descuento": "Requerido cuando el tipo es 'Porcentaje'."})
            # anula monto si quedó cargado
            if self.monto_descuento not in (None, Decimal("0"), 0):
                raise ValidationError({"monto_descuento": "No debe establecerse cuando el tipo es 'Porcentaje'."})

        elif self.tipo_descuento == "monto":
            if self.monto_descuento is None:
                raise ValidationError({"monto_descuento": "Requerido cuando el tipo es 'Monto fijo'."})
            # anula porcentaje si quedó cargado
            if self.porcentaje_descuento not in (None, Decimal("0"), 0):
                raise ValidationError({"porcentaje_descuento": "No debe establecerse cuando el tipo es 'Monto fijo'."})

        else:  # ninguno
            if (self.porcentaje_descuento not in (None, Decimal("0"), 0)) or \
               (self.monto_descuento not in (None, Decimal("0"), 0)):
                raise ValidationError("Si el tipo es 'Sin descuento', no establezcas porcentaje ni monto.")

    def calcular_descuento(self, base: Decimal) -> Decimal:
        """
        Devuelve el monto a descontar dado un precio base.
        - porcentaje: base * (porcentaje/100)
        - monto: el monto fijo
        - ninguno: 0
        """
        base = base or Decimal("0")
        if self.tipo_descuento == "porcentaje" and self.porcentaje_descuento:
            return (base * (self.porcentaje_descuento / Decimal("100"))).quantize(Decimal("0.01"))
        if self.tipo_descuento == "monto" and self.monto_descuento:
            return Decimal(self.monto_descuento).quantize(Decimal("0.01"))
        return Decimal("0.00")




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

    def flag_emoji(self):
        if not self.codigo_iso2:
            return ""
        code = self.codigo_iso2.upper()
        # Convierte ISO-2 en símbolos regionales 🇲🇽, 🇵🇦, 🇬🇹, etc.
        return "".join(chr(0x1F1E6 + (ord(c) - ord('A'))) for c in code if 'A' <= c <= 'Z')

    def __str__(self):
            # Si quieres que en *todos* lados salga con bandera:
            return f"{self.flag_emoji()} {self.nombre}"
            
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
class InformacionEscolar(models.Model):
    MODALIDAD_OPCIONES = [
        ("en_linea", "En línea"),
        ("presencial", "Presencial"),
    ]

    ESTATUS_OPCIONES_academico = [
        ("VIGENTE", "VIGENTE"),
        ("EGRESADO", "EGRESADO"),
        ("BAJA TEMPORAL", "BAJA TEMPORAL"),
        ("BAJA DEFINITIVA", "BAJA DEFINITIVA"),
        ("EN TITULACIÓN", "EN TITULACIÓN"),

        
    ]

    ESTATUS_OPCIONES_administrativo = [
        ("VIGENTE", "VIGENTE"),
        ("EGRESADO", "EGRESADO"),
        ("BAJA TEMPORAL", "BAJA TEMPORAL"),
        ("BAJA DEFINITIVA", "BAJA DEFINITIVA"),        
    ]

    programa = models.ForeignKey(Programa, on_delete=models.PROTECT,related_name='programa', null=True, blank=True)
    financiamiento = models.ForeignKey(Financiamiento,on_delete=models.SET_NULL, null=True,blank=True,related_name="alumnos",verbose_name="Financiamiento")
    precio_colegiatura = models.DecimalField("Precio colegiatura", max_digits=12, decimal_places=2)
    monto_descuento = models.DecimalField("Monto de descuento", max_digits=12, decimal_places=2, default=Decimal("0.00"))
    meses_programa = models.PositiveIntegerField("Meses de programa")
    precio_inscripcion = models.DecimalField("Precio de inscripción", max_digits=12, decimal_places=2, default=Decimal("0.00"))
    precio_titulacion = models.DecimalField("Precio de titulación", max_digits=12, decimal_places=2, default=Decimal("0.00"))
    precio_equivalencia = models.DecimalField("Precio de equivalencia", max_digits=12, decimal_places=2, default=Decimal("-1.00"))
    numero_reinscripciones = models.PositiveIntegerField("No. de reinscripciones", default=0)
    sede = models.ForeignKey("Sede", on_delete=models.SET_NULL, null=True, blank=True, related_name="alumnos")    
    precio_final = models.DecimalField("Precio Final", max_digits=12, decimal_places=2, null=True, blank=True)
    inicio_programa = models.DateField("Inicio del programa", null=True, blank=True)
    fin_programa = models.DateField("Fin del programa", null=True, blank=True)
    requiere_datos_de_facturacion = models.BooleanField("¿Requiere datos de facturación?", default=False)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)
    fecha_alta = models.DateTimeField(null=True, blank=True, help_text="Fecha en que el alumno se dio de alta en el sistema")
    grupo = models.CharField("Grupo", max_length=50, blank=True, null= True)
    modalidad = models.CharField("Modalidad",max_length=15,choices=MODALIDAD_OPCIONES,default="en_linea")
    matricula = models.CharField("Matrícula",max_length=64, null=True, blank= True)
    # CAMBIA estos dos: ahora son selects con choices
    estatus_academico = models.CharField("Estatus académico",max_length=20,choices=ESTATUS_OPCIONES_academico,blank=True,default="VIGENTE")# deja en blanco si quieres
    estatus_administrativo = models.CharField("Estatus administrativo",max_length=20,choices=ESTATUS_OPCIONES_administrativo,blank=True,default="VIGENTE")

    class Meta:
        verbose_name = "Informacion Escolar"
        verbose_name_plural = "Informacion Escolar"
        ordering = ["-creado_en"]

    def __str__(self):
        return f"Plan {self.programa} · fin {self.fin_programa}"



    def save(self, *args, **kwargs):
        # Descuento del financiamiento (si hay)
        desc_fin = Decimal("0.00")
        if self.financiamiento_id:
            try:
                desc_fin = self.financiamiento.calcular_descuento(self.precio_colegiatura or Decimal("0"))
            except Exception:
                desc_fin = Decimal("0.00")

        # Tu campo existente 'monto_descuento' (por si además aplicas otro descuento manual)
        desc_manual = self.monto_descuento or Decimal("0.00")

        if self.precio_final is None:
            bruto = (self.precio_colegiatura or Decimal("0")) - desc_fin - desc_manual
            self.precio_final = max(bruto, Decimal("0.00")).quantize(Decimal("0.01"))

        super().save(*args, **kwargs)

    @property
    def num_alumno(self):
        return self.alumno.numero_estudiante
############################################################################
class Alumno(models.Model):
    from django.utils import timezone
    from django.core.validators import RegexValidator
    SEXO_OPCIONES = [("Hombre","Hombre"),("Mujer","Mujer")]


    # ID oficial: número de estudiante tal cual en Excel
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL,null=True, blank=True,on_delete=models.SET_NULL,related_name="alumnos_creados")
    numero_estudiante = models.BigIntegerField("Número de estudiante", primary_key=True)
    user = models.OneToOneField(settings.AUTH_USER_MODEL,on_delete=models.SET_NULL,null=True, blank=True,related_name="perfil_alumno")    
    nombre = models.CharField('Nombre(s)',max_length=120)
    apellido_p = models.CharField("Apellido paterno", max_length=120, blank=True)
    apellido_m = models.CharField("Apellido materno", max_length=120, blank=True)
    email = models.EmailField("Correo electrónico personal",blank=True)
    email_institucional = models.EmailField("Correo electrónico institucional",blank=True,
        validators=[
            # obliga a que, si se llena, termine en @iuaf.edu.mx
            RegexValidator(
                regex=r"^[^@\s]+@iuaf\.edu\.mx$",
                message="El correo institucional debe ser @iuaf.edu.mx"
            )
        ],
        help_text="Usa siempre el correo @iuaf.edu.mx para Classroom/Zoom."
    )
    telefono = models.CharField(max_length=40, blank=True)    
    curp = models.CharField("CURP", max_length=18, null=True, blank=True)

    # NUEVOS CAMPOS
    pais = models.ForeignKey(Pais, on_delete=models.PROTECT, null=True, blank=True, related_name="alumnos")
    estado = models.ForeignKey(Estado, on_delete=models.PROTECT, null=True, blank=True, related_name="alumnos")            
    fecha_nacimiento = models.DateField(null=True, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)
    sexo = models.CharField("Sexo",max_length=20,choices=SEXO_OPCIONES,blank=True)

    informacionEscolar = models.OneToOneField('InformacionEscolar',on_delete=models.SET_NULL,null=True, blank=True,related_name='alumno',verbose_name="Plan financiero")        

    class Meta:
        ordering = ["-numero_estudiante"]
        indexes = [
            models.Index(fields=["numero_estudiante"]),
            models.Index(fields=["curp"]),
            models.Index(fields=["apellido_p", "apellido_m"]),
            models.Index(fields=["pais"]),
            models.Index(fields=["estado"]),
        ]

    # opcional: helper
    @staticmethod
    def for_user(user):
        qs = Alumno.objects.all()

        if not user.is_authenticated:
            return qs.none()

        # superuser o flags globales
        if user.is_superuser:
            return qs
        
         # Grupo "admisiones": solo sus alumnos
        if user.groups.filter(name="admisiones").exists():
            return qs.filter(created_by=user)
        
        profile = getattr(user, "profile", None)
        if not profile:
            return qs.none()

        sedes_ids = list(profile.sedes.values_list("id", flat=True))
        if not sedes_ids:
            return qs.none()

        base = qs.filter(informacionEscolar__sede_id__in=sedes_ids)

    

        return base


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
    
    @property
    def email_preferido(self):
        """Regresa el institucional si existe; si no, el personal."""
        return self.email_institucional or self.email
    


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
    
class Sede(models.Model):
    nombre = models.CharField("Nombre de la sede", max_length=150)

    # Vinculaciones opcionales:
    pais = models.ForeignKey(
        Pais, on_delete=models.PROTECT, null=True, blank=True, related_name="sedes"
    )
    estado = models.ForeignKey(
        Estado, on_delete=models.PROTECT, null=True, blank=True, related_name="sedes"
    )

    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Sede"
        verbose_name_plural = "Sedes"
        ordering = ["nombre"]
        # Evita duplicados del mismo nombre en el mismo país/estado
        constraints = [
            models.UniqueConstraint(
                fields=["nombre", "pais", "estado"],
                name="uniq_sede_nombre_pais_estado",
            )
        ]
        indexes = [
            models.Index(fields=["nombre"]),
            models.Index(fields=["pais"]),
            models.Index(fields=["estado"]),
            models.Index(fields=["activo"]),
        ]

    def __str__(self):
        if self.pais and self.estado:
            return f"{self.nombre} — {self.estado.nombre}, {self.pais.nombre}"
        if self.pais:
            return f"{self.nombre} — {self.pais.nombre}"
        return self.nombre

    def clean(self):
        # Si hay estado, debe pertenecer al país seleccionado (si hay país)
        if self.estado and self.pais and self.estado.pais_id != self.pais_id:
            from django.core.exceptions import ValidationError
            raise ValidationError({"estado": "El estado seleccionado no pertenece al país indicado."})
############################################################################################################
# app/models.py
import os
from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver


def doc_upload_path(instance, filename):
    """
    Guardar dentro de: documentos/<numero_estudiante>/<nombre-campo>/<archivo>
    """
    alumno_pk = instance.alumno_id or "sin_num"
    field_name = "otro"
    # Detecta el campo que se está guardando
    for f in instance._meta.get_fields():
        if isinstance(f, models.FileField):
            # si el archivo en memoria coincide
            if getattr(instance, f.name) and hasattr(getattr(instance, f.name), 'name'):
                if getattr(instance, f.name).name.endswith(filename):
                    field_name = f.name
                    break
    return os.path.join("documentos", str(alumno_pk), field_name, filename)


class DocumentosAlumno(models.Model):
    """
    Un set de documentos por alumno.
    """
    alumno = models.OneToOneField(
        "Alumno", on_delete=models.CASCADE, related_name="documentos"
    )

    acta_nacimiento = models.FileField("Acta de nacimiento", upload_to=doc_upload_path, null=True, blank=True)
    curp = models.FileField("CURP", upload_to=doc_upload_path, null=True, blank=True)
    certificado_estudios = models.FileField("Certificado de estudios", upload_to=doc_upload_path, null=True, blank=True)
    titulo_grado = models.FileField("Título o grado de estudios", upload_to=doc_upload_path, null=True, blank=True)
    solicitud_registro = models.FileField("Solicitud de registro", upload_to=doc_upload_path, null=True, blank=True)
    validacion_autenticidad = models.FileField("Documento de validación de autenticidad", upload_to=doc_upload_path, null=True, blank=True)
    carta_compromiso = models.FileField("Carta compromiso", upload_to=doc_upload_path, null=True, blank=True)
    carta_interes = models.FileField("Carta de interés académico", upload_to=doc_upload_path, null=True, blank=True)
    identificacion_oficial = models.FileField("Identificación oficial (INE, pasaporte, etc.)", upload_to=doc_upload_path, null=True, blank=True)

    # Campo “comodín” por si luego agregas otro documento sin migrar de inmediato
    otro_documento = models.FileField("Otro documento", upload_to=doc_upload_path, null=True, blank=True)

    fecha_ultima_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Documentos del alumno"
        verbose_name_plural = "Documentos de alumnos"

    def __str__(self):
        return f"Documentos — {self.alumno_id}"

    @property
    def total_subidos(self):
        files = [
            self.acta_nacimiento, self.curp, self.certificado_estudios, self.titulo_grado,
            self.solicitud_registro, self.validacion_autenticidad, self.carta_compromiso,
            self.carta_interes, self.identificacion_oficial, self.otro_documento
        ]
        return sum(1 for f in files if f)


@receiver(post_save, sender=Alumno)
def crear_contenedor_documentos(sender, instance, created, **kwargs):
    if created:
        DocumentosAlumno.objects.get_or_create(alumno=instance)

############################################################################################################
class PagoDiario(models.Model):
    folio = models.CharField(max_length=32, null=True, blank=True, db_index=True)  # no único, puede venir vacío
    sede = models.CharField(max_length=120, null=True, blank=True)
    nombre = models.CharField(max_length=200, null=True, blank=True)

    monto = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    grado = models.CharField(max_length=16, null=True, blank=True)
    forma_pago = models.CharField(max_length=32, null=True, blank=True)
    fecha = models.DateField(null=True, blank=True)

    concepto = models.CharField(max_length=120, null=True, blank=True)
    pago_detalle = models.CharField(max_length=200, null=True, blank=True)
    programa = models.CharField(max_length=200, null=True, blank=True)

    no_auto = models.CharField(max_length=64, null=True, blank=True)
    curp = models.CharField(max_length=24, null=True, blank=True)
    numero_alumno = models.IntegerField(null=True, blank=True)  # opcional: conservar valor crudo
    emision = models.CharField(max_length=64, null=True, blank=True)

    alumno = models.ForeignKey(Alumno, null=True, blank=True, on_delete=models.SET_NULL, related_name="pagos_diario")

    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-fecha"]
        indexes = [
            models.Index(fields=["folio"]),
            models.Index(fields=["fecha"]),
            models.Index(fields=["curp"]),
        ]

    def __str__(self):
        return f"PagoDiario folio={self.folio or '-'} fecha={self.fecha or '-'} monto={self.monto or '-'}"
############################################################################################################
class ContadorAlumno(models.Model):
    llave = models.CharField(max_length=32, unique=True, default="global")
    ultimo_numero = models.BigIntegerField(default=0)

    def __str__(self):
        return f"{self.llave} -> {self.ultimo_numero}"

#############################################################################################################
class ClipCredential(models.Model):
    """
    Credenciales para integración con Clip.
    Guarda tanto credenciales de sandbox como de producción.
    Mantén solo UNA instancia activa por environment si así lo deseas.
    """
    name = models.CharField(max_length=60, help_text="Nombre descriptivo (ej. 'Clip Prod', 'Clip Sandbox')")
    public_key = models.CharField(max_length=255, blank=True, null=True)
    secret_key = models.TextField(blank=True, null=True, help_text="Secret key (API secret). Guardar con precaución.")
    is_sandbox = models.BooleanField(default=True)
    active = models.BooleanField(default=False, help_text="Si está activa, será la usada por defecto en helpers.")
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-updated_at",)
        verbose_name = "Credencial Clip"
        verbose_name_plural = "Credenciales Clip"

    def __str__(self):
        env = "SANDBOX" if self.is_sandbox else "PROD"
        return f"{self.name} ({env}){' - activo' if self.active else ''}"

    def as_dict(self):
        return {
            "public_key": self.public_key,
            "secret_key": self.secret_key,
            "is_sandbox": self.is_sandbox,
            "active": self.active,
        }
    
    def clean(self):
        super().clean()
        if self.active:
            same = ClipCredential.objects.filter(is_sandbox=self.is_sandbox, active=True)
            if self.pk:
                same = same.exclude(pk=self.pk)
            if same.exists():
                raise ValidationError("Ya existe otra credencial activa para este ambiente (sandbox/producción).")
#############################################################################################################
class ClipPaymentOrder(models.Model):
    ESTADOS = [
        ("created", "Creada"),
        ("pending", "Pendiente"),
        ("paid", "Pagada"),
        ("failed", "Fallida"),
        ("canceled", "Cancelada"),
        ("expired", "Expirada"),
    ]

    alumno = models.ForeignKey("Alumno", on_delete=models.SET_NULL, null=True, related_name="ordenes_clip")
    cargo  = models.ForeignKey("Cargo", on_delete=models.SET_NULL, null=True, blank=True, related_name="ordenes_clip")

    # Datos económicos
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default="MXN")
    description = models.CharField(max_length=255, blank=True)

    # Estado de la orden
    status = models.CharField(max_length=12, choices=ESTADOS, default="created", db_index=True)

    # Identificadores/URLs de Clip
    clip_payment_id = models.CharField(max_length=64, blank=True, db_index=True)
    checkout_url = models.URLField(blank=True)  # si tu integración usa "link/checkout"

    # Metadatos crudos de Clip para auditoría / debug
    raw_request  = models.JSONField(null=True, blank=True)
    raw_response = models.JSONField(null=True, blank=True)
    last_webhook = models.JSONField(null=True, blank=True)

    # Idempotencia nuestra (evita duplicados al reintentar)
    idempotency_key = models.CharField(max_length=64, blank=True, db_index=True)

    # Timestamps
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"ClipOrder#{self.pk} {self.amount} {self.currency} [{self.status}]"

##############################################################################################################
class TwilioConfig(models.Model):
    ENV_CHOICES = (("sandbox", "sandbox"), ("prod", "prod"))  # añade esto

    name = models.CharField(max_length=64)
    env = models.CharField(max_length=16, choices=ENV_CHOICES, default="sandbox")
    account_sid = models.CharField(max_length=80)
    auth_token = models.CharField(max_length=80)
    messaging_service_sid = models.CharField(max_length=40, blank=True, null=True)
    sms_from = models.CharField(max_length=20, blank=True, null=True)
    whatsapp_from = models.CharField(max_length=25, blank=True, null=True)
    default_sms_to = models.CharField(max_length=20, blank=True, null=True)
    default_wa_to = models.CharField(max_length=25, blank=True, null=True)
    active = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-updated_at",)
        verbose_name = "Config de Twilio"
        verbose_name_plural = "Configs de Twilio"

    def __str__(self):
        env_label = dict(self.ENV_CHOICES).get(self.env, self.env)
        return f"{self.name} ({env_label}){' - activa' if self.active else ''}"

    def clean(self):
        # Asegura una sola activa por entorno
        super().clean()
        if self.active:
            qs = TwilioConfig.objects.filter(env=self.env, active=True)
            if self.pk:
                qs = qs.exclude(pk=self.pk)
            if qs.exists():
                raise ValidationError("Ya hay otra configuración activa para este entorno.")