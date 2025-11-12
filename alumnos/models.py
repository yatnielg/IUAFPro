from django.db import models
from django.core.exceptions import ValidationError
from django.conf import settings
from django.utils import timezone
from django.utils.functional import cached_property
from django.db.models import Min, Max, Q
from django.core.validators import MinValueValidator, MaxValueValidator

from decimal import Decimal
from collections import defaultdict
import re
import os
import unicodedata

from django.utils.functional import cached_property

# ============================================================
# Utilidades
# ============================================================

def _slugify_filename(name: str) -> str:
    base, ext = os.path.splitext(name)
    base = unicodedata.normalize("NFKD", base).encode("ascii", "ignore").decode("ascii")
    base = "".join(c if c.isalnum() or c in ("-", "_") else "-" for c in base).strip("-_")
    return f"{base}{ext.lower()}"

def doc_upload_path(instance, filename):
    """
    Ruta: documentos/<alumno>/<infoescolar_id>/<tipo_slug>/<archivo>
    """
    alumno_pk = getattr(instance.info_escolar, "alumno_id", None) or "sin_alumno"
    tipo_slug = instance.tipo.slug if instance.tipo_id else "sin-tipo"
    safe = _slugify_filename(filename)
    return os.path.join("documentos", str(alumno_pk), str(instance.info_escolar_id), tipo_slug, safe)

# ============================================================
# Documentación académica flexible por Programa
# ============================================================

class DocumentoTipo(models.Model):
    """
    Catálogo de tipos de documento (Acta, CURP, Certificado, etc.)
    """
    slug = models.SlugField(max_length=60, unique=True)
    nombre = models.CharField(max_length=120)
    descripcion = models.TextField(blank=True)

    # NUEVOS CAMPOS
    presentacion = models.CharField(
        "Presentación",
        max_length=120,
        blank=True,
        help_text="Ej.: Original / Original y copia / 2 copias / 1 copia."
    )
    observaciones = models.TextField(
        blank=True,
        help_text="Notas u observaciones adicionales para el alumno o control interno."
    )
    orden = models.PositiveIntegerField(
        default=0,
        db_index=True,
        help_text="Orden de aparición en listados y formularios."
    )


    multiple = models.BooleanField(
        default=False,
        help_text="Si permite más de un archivo por alumno/plan."
    )
    activo = models.BooleanField(default=True)

    class Meta:
            ordering = ["orden", "nombre"]  # antes: ["nombre"]
            verbose_name = "Tipo de documento"
            verbose_name_plural = "Tipos de documento"
            indexes = [
                models.Index(fields=["orden"]),
                models.Index(fields=["activo"]),
            ]

    def __str__(self):
        return f"{self.nombre} ({self.slug})"


class ProgramaDocumentoRequisito(models.Model):
    """
    Qué documentos requiere un Programa (con reglas).
    """
    APLICA_CHOICES = (
        ("todos", "Todos"),
        ("solo_extranjeros", "Solo extranjeros"),
        ("solo_nacionales", "Solo nacionales"),
    )

    programa = models.ForeignKey("Programa", on_delete=models.CASCADE, related_name="requisitos_documentales")
    tipo = models.ForeignKey(DocumentoTipo, on_delete=models.PROTECT, related_name="requisitos_programa")
    obligatorio = models.BooleanField(default=True)
    minimo = models.PositiveIntegerField(default=1, help_text="Cantidad mínima de archivos requeridos.")
    maximo = models.PositiveIntegerField(default=1, help_text="Cantidad máxima permitida (ignorado si multiple=False).")
    activo = models.BooleanField(default=True)

    aplica_a = models.CharField(
        max_length=20,
        choices=APLICA_CHOICES,
        default="todos",
        help_text="Define si este documento lo deben subir todos, solo extranjeros, o solo nacionales."
    )

    class Meta:
        unique_together = [("programa", "tipo")]
        ordering = ["programa__codigo", "tipo__nombre"]
        verbose_name = "Requisito documental de Programa"
        verbose_name_plural = "Requisitos documentales de Programas"

    def __str__(self):
        ob = "OBLIG" if self.obligatorio else "OPC"
        return f"{self.programa.codigo} - {self.tipo.nombre} [{ob} min={self.minimo} max={self.maximo}]"


class DocumentoAlumno(models.Model):
    """
    Documento subido por un alumno para un plan (InformacionEscolar) y un tipo.
    Permite múltiples archivos si el tipo o el requisito lo permiten.
    """
    info_escolar = models.ForeignKey(
        "InformacionEscolar",
        on_delete=models.CASCADE,
        related_name="documentos"
    )
    tipo = models.ForeignKey(DocumentoTipo, on_delete=models.PROTECT, related_name="documentos")
    archivo = models.FileField(upload_to=doc_upload_path)

    # trazabilidad/estado
    subido_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="docs_subidos")
    verificado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="docs_verificados")
    verificado_en = models.DateTimeField(null=True, blank=True)
    valido = models.BooleanField(default=None, null=True, help_text="¿Validado documentalmente?")
    notas = models.TextField(blank=True)

    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-creado_en"]
        indexes = [
            models.Index(fields=["info_escolar", "tipo"]),
        ]
        verbose_name = "Documento del alumno"
        verbose_name_plural = "Documentos del alumno"

    def __str__(self):
        return f"{self.info_escolar_id} · {self.tipo.nombre} · {os.path.basename(self.archivo.name)}"

# ============================================================
# Users / perfiles
# ============================================================

class UserProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    sedes = models.ManyToManyField("Sede", blank=True)

    # flags de alcance global
    puede_ver_todo = models.BooleanField(default=False)
    puede_editar_todo = models.BooleanField("Puede editar", default=False)
    ver_todos_los_pagos = models.BooleanField(default=False, help_text="Si está activo, el usuario verá todos los pagos (sin límite de años).")

    def __str__(self):
        return f"Perfil de {self.user}"

# ============================================================
# Extracción de nombre desde movimientos bancarios (helpers)
# ============================================================

_STOPWORDS = {
    "ABONO", "CARGO", "INTERBANCARIO", "SUCURSAL", "REFERENCIA", "NUMERICA",
    "NUMÉRICA", "ALFANUMERICA", "ALFANUMÉRICA", "NOMBRE", "EMISOR",
    "NO", "DE", "AUTORIZACION", "AUTORIZACIÓN", "FECHA", "TIPO", "MONTO",
    "SPEI", "TRANSFERENCIA", "CLABE", "CUENTA", "DEPOSITO", "DEPÓSITO", "COMISION", "IVA",
    "RECEPCION", "INSTITUTO", "UNIVERSITARIO", "FORMACIO", "ADMINISTRACION", "PAQUETE", "SERVICIOS", "PYME",
}
_LABEL_RE = re.compile(
    r"(?:Referencia\s+alfanum(?:e|é)rica|Nombre\s+del\s+Emisor)\s*:\s*([^\n\r|]+)",
    flags=re.IGNORECASE
)
_NAME_CANDIDATE_RE = re.compile(
    r"\b([A-ZÁÉÍÓÚÑ]{2,}(?:[-\.]?[A-ZÁÉÍÓÚÑ]{2,})?(?:\s+[A-ZÁÉÍÓÚÑ]{2,}(?:[-\.]?[A-ZÁÉÍÓÚÑ]{2,})?){2,5})\b"
)

def _cleanup_spaces(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()

def _title_person(s: str) -> str:
    if not s:
        return s
    parts_lower = {"DE", "DEL", "LA", "LAS", "LOS", "Y", "MC", "VON", "VAN", "DA", "DI", "DOS", "DU"}
    out = []
    for w in s.split():
        uw = w.upper()
        out.append(uw.lower() if uw in parts_lower else uw.capitalize())
    return " ".join(out)

def _best_name_span(text: str) -> str | None:
    if not text:
        return None
    txt = _cleanup_spaces(text).replace("|", " ")
    best = None
    best_len = 0
    for m in _NAME_CANDIDATE_RE.finditer(txt):
        cand = _cleanup_spaces(m.group(1))
        tokens = [t for t in cand.split() if t.upper() not in _STOPWORDS]
        if len(tokens) >= 3:
            cand2 = " ".join(tokens)
            if len(tokens) > best_len:
                best = cand2
                best_len = len(tokens)
    return best

# ============================================================
# Movimientos bancarios
# ============================================================

class MovimientoBanco(models.Model):
    alumno_asignado = models.ForeignKey('Alumno', null=True, blank=True, on_delete=models.SET_NULL, related_name='movimientos_banco')
    pago_creado = models.ForeignKey('PagoDiario', null=True, blank=True, on_delete=models.SET_NULL,related_name='movimiento_banco')    
    conciliado = models.BooleanField(default=False, db_index=True)
    conciliado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,related_name='conciliaciones_banco')
    conciliado_en = models.DateTimeField(null=True, blank=True)


    fecha = models.DateField(null=True, blank=True, db_index=True)
    tipo = models.CharField(max_length=120, null=True, blank=True, db_index=True)
    monto = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True, db_index=True)

    SIGNO_CHOICES = ((-1, "Cargo"), (1, "Abono"))
    signo = models.SmallIntegerField(choices=SIGNO_CHOICES, null=True, blank=True)

    sucursal = models.CharField(max_length=50, null=True, blank=True, db_index=True)
    referencia_numerica = models.CharField(max_length=50, null=True, blank=True, db_index=True)
    referencia_alfanumerica = models.TextField(null=True, blank=True)
    concepto = models.TextField(null=True, blank=True)
    autorizacion = models.CharField(max_length=50, null=True, blank=True, db_index=True)
    emisor_nombre = models.CharField(max_length=200, null=True, blank=True, db_index=True)
    institucion_emisora = models.CharField(max_length=120, null=True, blank=True, db_index=True)

    descripcion_raw = models.TextField(null=True, blank=True)

    source_sheet_id = models.CharField(max_length=128, null=True, blank=True, db_index=True)
    source_sheet_name = models.CharField(max_length=128, null=True, blank=True, db_index=True)
    source_gid = models.CharField(max_length=32, null=True, blank=True, db_index=True)
    source_row = models.IntegerField(null=True, blank=True)

    uid_hash = models.CharField(max_length=40, unique=True, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    nombre_detectado_save = models.CharField(max_length=200, null=True, blank=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=["fecha", "tipo"]),
            models.Index(fields=["referencia_numerica", "autorizacion"]),
            models.Index(fields=["emisor_nombre"]),
            models.Index(fields=["institucion_emisora"]),
        ]
        ordering = ["id"]

    def __str__(self):
        return f"[{self.fecha}] {self.tipo or 'Movimiento'} ${self.monto or 0}"

    @cached_property
    def nombre_detectado(self) -> str:
        for source in (self.referencia_alfanumerica, self.emisor_nombre):
            nm = _best_name_span(source or "")
            if nm:
                return _title_person(nm)
        if self.descripcion_raw:
            for lab in _LABEL_RE.findall(self.descripcion_raw):
                nm = _best_name_span(lab)
                if nm:
                    return _title_person(nm)
            nm = _best_name_span(self.descripcion_raw)
            if nm:
                return _title_person(nm)
        return ""
    
    @property
    def total_pagos_conciliados(self):
        return sum((p.monto or 0) for p in self.pagos_creados.all())

    @property
    def restante_por_conciliar(self):
        return (self.monto or 0) - self.total_pagos_conciliados
    
    def deshacer_conciliacion(self):
        """Deshace la conciliación: elimina pagos y resetea banderas."""
        if not self.conciliado:
            return False, "Este movimiento no está conciliado."

        # elimina los pagos asociados (si hay uno o varios)
        pagos = PagoDiario.objects.filter(movimiento_banco=self)
        num = pagos.count()
        pagos.delete()

        # resetea campos
        self.conciliado = False
        self.conciliado_por = None
        self.conciliado_en = None
        self.pago_creado = None
        self.save(update_fields=["conciliado", "conciliado_por", "conciliado_en", "pago_creado"])
        return True, f"Conciliación revertida. Se eliminaron {num} pagos."

# ============================================================
# Catálogos financieros y geográficos
# ============================================================

class Financiamiento(models.Model):
    TIPO_DESCUENTO = [
        ("ninguno", "Sin descuento"),
        ("porcentaje", "Porcentaje"),
        ("monto", "Monto fijo"),
    ]

    programa = models.ForeignKey("Programa", blank=True, null=True, on_delete=models.PROTECT, related_name="financiamientos", verbose_name="Programa")
    beca = models.CharField("Beca", max_length=120, blank=True)
    tipo_descuento = models.CharField("Tipo de descuento", max_length=20, choices=TIPO_DESCUENTO, default="ninguno")
    porcentaje_descuento = models.DecimalField("Porcentaje de descuento", max_digits=5, decimal_places=2, null=True, blank=True,
                                               validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))])
    monto_descuento = models.DecimalField("Monto fijo a descontar", max_digits=12, decimal_places=2, null=True, blank=True,
                                          validators=[MinValueValidator(Decimal("0.00"))])

    class Meta:
        verbose_name = "Financiamiento"
        verbose_name_plural = "Financiamientos"
        ordering = ["id"]

    def __str__(self):
        etiqueta = "Sin nombre" if not self.beca else self.beca
        if self.tipo_descuento == "porcentaje" and self.porcentaje_descuento is not None:
            etiqueta = f"{etiqueta} — {self.porcentaje_descuento}%"
        elif self.tipo_descuento == "monto" and self.monto_descuento is not None:
            etiqueta = f"{etiqueta} — Descuento de ${self.monto_descuento}"
        return f"[{self.programa.codigo if self.programa else ''}] {etiqueta}"

    def clean(self):
        if self.tipo_descuento == "porcentaje":
            if self.porcentaje_descuento is None:
                raise ValidationError({"porcentaje_descuento": "Requerido cuando el tipo es 'Porcentaje'."})
            if self.monto_descuento not in (None, Decimal("0"), 0):
                raise ValidationError({"monto_descuento": "No debe establecerse cuando el tipo es 'Porcentaje'."})
        elif self.tipo_descuento == "monto":
            if self.monto_descuento is None:
                raise ValidationError({"monto_descuento": "Requerido cuando el tipo es 'Monto fijo'."})
            if self.porcentaje_descuento not in (None, Decimal("0"), 0):
                raise ValidationError({"porcentaje_descuento": "No debe establecerse cuando el tipo es 'Monto fijo'."})
        else:
            if (self.porcentaje_descuento not in (None, Decimal("0"), 0)) or (self.monto_descuento not in (None, Decimal("0"), 0)):
                raise ValidationError("Si el tipo es 'Sin descuento', no establezcas porcentaje ni monto.")


    def calcular_descuento(self, base: Decimal) -> Decimal:
        base = base or Decimal("0")
        if self.tipo_descuento == "porcentaje" and self.porcentaje_descuento:
            return (base * (self.porcentaje_descuento / Decimal("100"))).quantize(Decimal("0.01"))
        if self.tipo_descuento == "monto" and self.monto_descuento:
            return Decimal(self.monto_descuento).quantize(Decimal("0.01"))
        return Decimal("0.00")

class Pais(models.Model):
    nombre = models.CharField(max_length=120, unique=True)
    codigo_iso2 = models.CharField("Código ISO-2", max_length=2, blank=True)
    codigo_iso3 = models.CharField("Código ISO-3", max_length=3, blank=True)
    requiere_estado = models.BooleanField("¿Requiere estado/provincia?", default=False)

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
        return "".join(chr(0x1F1E6 + (ord(c) - ord('A'))) for c in code if 'A' <= c <= 'Z')

    def __str__(self):
        return f"{self.flag_emoji()} {self.nombre}"


class Estado(models.Model):
    pais = models.ForeignKey(Pais, on_delete=models.CASCADE, related_name="estados")
    nombre = models.CharField(max_length=120)

    class Meta:
        verbose_name = "Estado/Provincia"
        verbose_name_plural = "Estados/Provincias"
        ordering = ["pais__nombre", "nombre"]
        unique_together = [("pais", "nombre")]
        indexes = [models.Index(fields=["pais", "nombre"])]

    def __str__(self):
        return f"{self.nombre} ({self.pais.nombre})"

#################################################################################################
from django.core.validators import MinValueValidator

class ReinscripcionHito(models.Model):
    programa = models.ForeignKey(
        "Programa",
        on_delete=models.CASCADE,
        related_name="reinscripciones_hitos",
        verbose_name="Programa",
    )
    nombre = models.CharField(max_length=120, blank=True, help_text="Etiqueta opcional (p.ej. 'Mes 9').")
    meses_offset = models.PositiveIntegerField(
        "Mes de cobro",
        validators=[MinValueValidator(1)],
        help_text="Mes contado desde el inicio (1=primer mes, 9=noveno mes, etc.)"
    )
    monto = models.DecimalField(
        "Monto (opcional)",
        max_digits=12, decimal_places=2,
        null=True, blank=True,
        help_text="Si lo dejas vacío, usa Programa.reinscripcion."
    )
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Hito de reinscripción"
        verbose_name_plural = "Hitos de reinscripción"
        ordering = ["meses_offset", "id"]
        constraints = [
            # Evita duplicar el mismo mes dentro del mismo programa
            models.UniqueConstraint(
                fields=["programa", "meses_offset"],
                name="uniq_hito_programa_mes"
            )
        ]
        indexes = [
            models.Index(fields=["programa", "meses_offset"]),
            models.Index(fields=["activo"]),
        ]

    def __str__(self):
        tag = self.nombre or f"Mes {self.meses_offset}"
        return f"{self.programa.codigo} · {tag}"

# ============================================================
# Programas y estatus
# ============================================================

class Programa(models.Model):
    codigo = models.CharField("Programas (código)", max_length=20, unique=True)
    nombre = models.CharField("Nombre de Cursos", max_length=200)
    meses_programa = models.PositiveIntegerField("Meses Programa", validators=[MinValueValidator(1)])

    rvoe_clave = models.CharField("R.V.O.E.", max_length=50, blank=True, db_index=True)
    rvoe_fecha = models.DateField("Fecha R.V.O.E.", null=True, blank=True)
    rvoe_emisor = models.CharField("Emisor R.V.O.E. (SEP/Estado)", max_length=120, blank=True)
    rvoe_url = models.URLField("URL del acuerdo (opcional)", blank=True)

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


class BaseEstatus(models.Model):
    codigo = models.CharField(max_length=50, unique=True)
    nombre = models.CharField(max_length=100)
    orden = models.PositiveIntegerField(default=0)
    activo = models.BooleanField(default=True)

    class Meta:
        abstract = True
        ordering = ["orden", "nombre"]

    def __str__(self):
        return self.nombre


class EstatusAcademico(BaseEstatus):
    class Meta(BaseEstatus.Meta):
        verbose_name = "Estatus académico"
        verbose_name_plural = "Estatus académicos"


class EstatusAdministrativo(BaseEstatus):
    class Meta(BaseEstatus.Meta):
        verbose_name = "Estatus administrativo"
        verbose_name_plural = "Estatus administrativos"



#############################################################################################
class Grupo(models.Model):
    """
    Grupo académico asociado a un Programa.
    """
    programa = models.ForeignKey(
        "Programa",
        on_delete=models.CASCADE,
        related_name="grupos",
        verbose_name="Programa",
        db_index=True,
    )
    codigo = models.SlugField(
        "Código de grupo",
        max_length=60,
        help_text="Identificador corto (sin espacios). Ej.: a-2025-1",
    )
    nombre = models.CharField(
        "Nombre visible",
        max_length=120,
        help_text="Etiqueta que verá el usuario. Ej.: A 2025-1 Vespertino",
    )
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Grupo"
        verbose_name_plural = "Grupos"
        ordering = ["programa__codigo", "nombre"]
        unique_together = [("programa", "codigo")]
        indexes = [
            models.Index(fields=["programa", "codigo"]),
            models.Index(fields=["activo"]),
        ]

    def __str__(self):
        return f"{self.programa.codigo} — {self.nombre}"

# ============================================================
# InformacionEscolar (plan) y documentos asociados
# ============================================================

class InformacionEscolar(models.Model):
    MODALIDAD_OPCIONES = [("en_linea", "En línea"), ("presencial", "Presencial")]

    programa = models.ForeignKey(Programa, on_delete=models.PROTECT, related_name="programa", null=True, blank=True)
    financiamiento = models.ForeignKey("Financiamiento", on_delete=models.SET_NULL, null=True, blank=True, related_name="alumnos", verbose_name="Financiamiento")

    precio_colegiatura = models.DecimalField("Precio colegiatura", max_digits=12, decimal_places=2, default=Decimal("0.00"))
    monto_descuento = models.DecimalField("Monto de descuento", max_digits=12, decimal_places=2, default=Decimal("0.00"))
    meses_programa = models.PositiveIntegerField("Meses de programa")
    precio_inscripcion = models.DecimalField("Precio de inscripción", max_digits=12, decimal_places=2, default=Decimal("0.00"))
    precio_reinscripcion = models.DecimalField("Precio de reinscripción", max_digits=12, decimal_places=2, default=Decimal("0.00"))
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
    # NUEVO: vínculo al modelo Grupo
    grupo_nuevo = models.ForeignKey(
        "Grupo",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="planes",
        verbose_name="Grupo (nuevo)",
        help_text="Selecciona un grupo del catálogo. Si está vacío se usará el campo 'Grupo' (LEGACY).",
    )

    # LEGACY (DEPRECATED): mantener mientras migras
    grupo = models.CharField(
        "Grupo",
        max_length=50,
        blank=True, null=True,
        help_text="LEGACY / DEPRECADO: Se usará sólo si no hay 'Grupo (nuevo)'."
    )
    modalidad = models.CharField("Modalidad", max_length=15, choices=MODALIDAD_OPCIONES, default="en_linea")
    matricula = models.CharField("Matrícula", max_length=64, null=True, blank=True)

    bienvenida_enviada = models.BooleanField(default=False, db_index=True, verbose_name="Bienvenida enviada")
    bienvenida_enviada_en = models.DateTimeField(null=True, blank=True, verbose_name="Bienvenida enviada en")
    bienvenida_enviada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="bienvenidas_enviadas",
        verbose_name="Bienvenida enviada por"
    )

    estatus_academico = models.ForeignKey("EstatusAcademico", on_delete=models.PROTECT, related_name="informaciones_academicas",
                                          verbose_name="Estatus académico", null=True, blank=True)
    estatus_administrativo = models.ForeignKey("EstatusAdministrativo", on_delete=models.PROTECT, related_name="informaciones_administrativas",
                                               verbose_name="Estatus administrativo", null=True, blank=True)

    class Meta:
        verbose_name = "Informacion Escolar"
        verbose_name_plural = "Informacion Escolar"
        ordering = ["-creado_en"]

    def __str__(self):
        return f"Plan {self.programa} · fin {self.fin_programa}"

    def save(self, *args, **kwargs):
        desc_fin = Decimal("0.00")
        if self.financiamiento_id:
            try:
                desc_fin = self.financiamiento.calcular_descuento(self.precio_colegiatura or Decimal("0"))
            except Exception:
                desc_fin = Decimal("0.00")
        desc_manual = self.monto_descuento or Decimal("0.00")

        if self.precio_final is None:
            bruto = (self.precio_colegiatura or Decimal("0")) - desc_fin - desc_manual
            self.precio_final = max(bruto, Decimal("0.00")).quantize(Decimal("0.01"))
        super().save(*args, **kwargs)

    @property
    def num_alumno(self):
        return getattr(self, "alumno", None) and self.alumno.numero_estudiante

    # === Helpers de documentos ===
    def requisitos_documentales(self):
        if not self.programa_id:
            return ProgramaDocumentoRequisito.objects.none()
        return self.programa.requisitos_documentales.filter(activo=True, tipo__activo=True).select_related("tipo")

    def documentos_por_tipo(self):
        out = defaultdict(list)
        for d in self.documentos.select_related("tipo").all():
            out[d.tipo_id].append(d)
        return out

    def resumen_cumplimiento(self):
        reqs = self.requisitos_documentales()
        por_tipo = self.documentos_por_tipo()
        resumen = []
        for req in reqs:
            subidos = len(por_tipo.get(req.tipo_id, []))
            faltan = max(req.minimo - subidos, 0)
            cumple = (subidos >= req.minimo) if req.obligatorio else True
            resumen.append({
                "tipo": req.tipo,
                "obligatorio": req.obligatorio,
                "minimo": req.minimo,
                "maximo": req.maximo,
                "subidos": subidos,
                "cumple": cumple,
                "faltan": faltan,
            })
        return resumen

    def faltantes_obligatorios(self):
        return [row["tipo"] for row in self.resumen_cumplimiento() if row["obligatorio"] and not row["cumple"]]

    @property
    def total_documentos(self) -> int:
        return self.documentos.count()

    @property
    def fecha_ultima_actualizacion_docs(self):
        return self.documentos.aggregate(m=Max("actualizado_en"))["m"]
    
    @property
    def grupo_mostrado(self) -> str:
        """
        Devuelve el nombre del Grupo nuevo si existe; en caso contrario,
        devuelve el valor legacy del CharField 'grupo'.
        """
        if self.grupo_nuevo_id and self.grupo_nuevo:
            return self.grupo_nuevo.nombre
        return self.grupo or ""

# ============================================================
# Alumnos y pagos
# ============================================================

class Alumno(models.Model):
    from django.core.validators import RegexValidator
    SEXO_OPCIONES = [("Hombre", "Hombre"), ("Mujer", "Mujer")]

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="alumnos_creados")
    numero_estudiante = models.BigIntegerField("Número de estudiante", primary_key=True)
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="perfil_alumno")
    nombre = models.CharField('Nombre(s)', max_length=120)
    apellido_p = models.CharField("Apellido paterno", max_length=120, blank=True)
    apellido_m = models.CharField("Apellido materno", max_length=120, blank=True)
    email = models.EmailField("Correo electrónico personal", blank=True)
    email_institucional = models.EmailField(
        "Correo electrónico institucional", blank=True,
        validators=[RegexValidator(regex=r"^[^@\s]+@iuaf\.edu\.mx$", message="El correo institucional debe ser @iuaf.edu.mx")],
        help_text="Usa siempre el correo @iuaf.edu.mx para Classroom/Zoom."
    )
    telefono = models.CharField(max_length=40, blank=True)
    curp = models.CharField("CURP", max_length=18, null=True, blank=True)

    pais = models.ForeignKey(Pais, on_delete=models.PROTECT, null=True, blank=True, related_name="alumnos")
    estado = models.ForeignKey(Estado, on_delete=models.PROTECT, null=True, blank=True, related_name="alumnos")
    fecha_nacimiento = models.DateField(null=True, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)
    sexo = models.CharField("Sexo", max_length=20, choices=SEXO_OPCIONES, blank=True)

    informacionEscolar = models.OneToOneField('InformacionEscolar', on_delete=models.SET_NULL, null=True, blank=True,
                                              related_name='alumno', verbose_name="Plan financiero")

    class Meta:
        ordering = ["-numero_estudiante"]
        indexes = [
            models.Index(fields=["numero_estudiante"]),
            models.Index(fields=["curp"]),
            models.Index(fields=["apellido_p", "apellido_m"]),
            models.Index(fields=["pais"]),
            models.Index(fields=["estado"]),
        ]

    @staticmethod
    def for_user(user):
        qs = Alumno.objects.all()
        if not user.is_authenticated:
            return qs.none()
        if user.is_superuser:
            return qs
        if user.groups.filter(name="admisiones").exists():
            return qs.filter(created_by=user)
        profile = getattr(user, "profile", None)
        if not profile:
            return qs.none()
        sedes_ids = list(profile.sedes.values_list("id", flat=True))
        if not sedes_ids:
            return qs.none()
        return qs.filter(informacionEscolar__sede_id__in=sedes_ids)

    @property
    def programa_clave(self):
        # Accede al programa a través del plan
        if self.informacionEscolar and self.informacionEscolar.programa_id:
            return self.informacionEscolar.programa.codigo
        return ""

    def clean(self):
        if self.pais and self.pais.requiere_estado:
            if not self.estado:
                raise ValidationError({"estado": "Este país requiere seleccionar un estado/provincia."})
            if self.estado and self.estado.pais_id != self.pais_id:
                raise ValidationError({"estado": "El estado seleccionado no pertenece al país indicado."})
        if self.pais and not self.pais.requiere_estado and self.estado:
            self.estado = None

    def __str__(self):
        return f"{self.numero_estudiante} - {self.nombre} {self.apellido_p}".strip()

    @property
    def email_preferido(self):
        return self.email_institucional or self.email


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
    metodo = models.CharField(max_length=40, blank=True)
    banco = models.CharField(max_length=60, blank=True)
    referencia = models.CharField(max_length=80, blank=True)
    descripcion = models.TextField(blank=True)
    conciliado = models.BooleanField(default=False)
    cargo = models.ForeignKey(Cargo, null=True, blank=True, on_delete=models.SET_NULL, related_name="pagos")

    def __str__(self):
        return f"Pago {self.id} - {self.alumno_id or 'SIN ALUMNO'} - {self.monto}"

# ============================================================
# Sedes
# ============================================================

class Sede(models.Model):
    nombre = models.CharField("Nombre de la sede", max_length=150)
    pais = models.ForeignKey(Pais, on_delete=models.PROTECT, null=True, blank=True, related_name="sedes")
    estado = models.ForeignKey(Estado, on_delete=models.PROTECT, null=True, blank=True, related_name="sedes")
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Sede"
        verbose_name_plural = "Sedes"
        ordering = ["nombre"]
        constraints = [
            models.UniqueConstraint(fields=["nombre", "pais", "estado"], name="uniq_sede_nombre_pais_estado"),
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
        if self.estado and self.pais and self.estado.pais_id != self.pais_id:
            raise ValidationError({"estado": "El estado seleccionado no pertenece al país indicado."})

# ============================================================
# Otros modelos operativos
# ============================================================

class PagoDiario(models.Model):
    

    payment_record = models.OneToOneField("cobros.PaymentRecord", null=True, blank=True, on_delete=models.SET_NULL, related_name="pago_diario")
    movimiento = models.ForeignKey('MovimientoBanco', null=True, blank=True, on_delete=models.SET_NULL, related_name="pagos_creados")
    folio = models.CharField(max_length=32, null=True, blank=True, db_index=True)
    sede = models.CharField(max_length=120, null=True, blank=True)
    nombre = models.CharField(max_length=200, null=True, blank=True)

    monto = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    grado = models.CharField(max_length=16, null=True, blank=True)
    forma_pago = models.CharField(max_length=128, null=True, blank=True)
    fecha = models.DateField(null=True, blank=True)

    concepto = models.CharField(max_length=120, null=True, blank=True)
    pago_detalle = models.CharField(max_length=200, null=True, blank=True)
    programa = models.CharField(max_length=200, null=True, blank=True)

    no_auto = models.CharField(max_length=64, null=True, blank=True)
    curp = models.CharField(max_length=24, null=True, blank=True)
    numero_alumno = models.IntegerField(null=True, blank=True)
    emision = models.CharField(max_length=64, null=True, blank=True)

    alumno = models.ForeignKey(Alumno, null=True, blank=True, on_delete=models.SET_NULL, related_name="pagos_diario")

    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    pago_oportuno = models.BooleanField(default=True)

    class Meta:
        ordering = ["-fecha"]
        indexes = [
            models.Index(fields=["folio"]),
            models.Index(fields=["fecha"]),
            models.Index(fields=["curp"]),
            models.Index(fields=["creado_en"]),
        ]

    def __str__(self):
        return f"PagoDiario folio={self.folio or '-'} fecha={self.fecha or '-'} monto={self.monto or '-'}"


class ContadorAlumno(models.Model):
    llave = models.CharField(max_length=32, unique=True, default="global")
    ultimo_numero = models.BigIntegerField(default=0)

    def __str__(self):
        return f"{self.llave} -> {self.ultimo_numero}"


class ClipCredential(models.Model):
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
    cargo = models.ForeignKey("Cargo", on_delete=models.SET_NULL, null=True, blank=True, related_name="ordenes_clip")

    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default="MXN")
    description = models.CharField(max_length=255, blank=True)

    status = models.CharField(max_length=12, choices=ESTADOS, default="created", db_index=True)
    clip_payment_id = models.CharField(max_length=64, blank=True, db_index=True)
    checkout_url = models.URLField(blank=True)

    raw_request = models.JSONField(null=True, blank=True)
    raw_response = models.JSONField(null=True, blank=True)
    last_webhook = models.JSONField(null=True, blank=True)

    idempotency_key = models.CharField(max_length=64, blank=True, db_index=True)

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"ClipOrder#{self.pk} {self.amount} {self.currency} [{self.status}]"


class TwilioConfig(models.Model):
    ENV_CHOICES = (("sandbox", "sandbox"), ("prod", "prod"))

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
        super().clean()
        if self.active:
            qs = TwilioConfig.objects.filter(env=self.env, active=True)
            if self.pk:
                qs = qs.exclude(pk=self.pk)
            if qs.exists():
                raise ValidationError("Ya hay otra configuración activa para este entorno.")
            
############################################################################################################################
import secrets

def generate_token():
    # ~256 bits en Base64 URL-safe (muy difícil de adivinar)
    return secrets.token_urlsafe(32)

class UploadInvite(models.Model):
    alumno = models.ForeignKey("alumnos.Alumno", on_delete=models.CASCADE, related_name="upload_invites")
    token = models.CharField(max_length=200, unique=True, default=generate_token)
    expires_at = models.DateTimeField()                # p.ej. ahora + 7 días
    max_uses = models.PositiveIntegerField(default=0)  # 0 = ilimitado hasta expirar
    uses = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    created_by = models.ForeignKey("auth.User", null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    def is_valid(self):
        if not self.is_active:
            return False
        if self.expires_at and timezone.now() > self.expires_at:
            return False
        if self.max_uses and self.uses >= self.max_uses:
            return False
        return True

    def __str__(self):
        return f"Invite {self.alumno_id} ({'ok' if self.is_valid() else 'expired'})"