# forms.py
from django import forms
from django.db.models import Q, Count
from django.forms import modelformset_factory, inlineformset_factory
from decimal import Decimal

from .models import (
    Alumno, Estado, Pais,
    InformacionEscolar,
    DocumentoAlumno, DocumentoTipo, ProgramaDocumentoRequisito,
)
from alumnos import models

# ---------- Widgets helpers ----------
class ClearableFileInputAccept(forms.ClearableFileInput):
    """
    Widget para inputs de archivo con 'accept' y clase adecuada para que no quede oculto
    por estilos del theme (usa form-control-file en Bootstrap/Material).
    """
    def __init__(self, *args, **kwargs):
        attrs = kwargs.setdefault("attrs", {})
        # PDF e imágenes por defecto; ajusta si quieres restringir más
        attrs.setdefault("accept", ".pdf,.png,.jpg,.jpeg")
        css = attrs.get("class", "")
        # clase apropiada para file inputs
        attrs["class"] = (css + " form-control-file").strip()
        super().__init__(*args, **kwargs)


# ============================================================
#  ALUMNO
# ============================================================
class AlumnoForm(forms.ModelForm):
    fecha_nacimiento = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        input_formats=["%Y-%m-%d"],
    )

    @staticmethod
    def _pais_label(pais: Pais) -> str:
        return str(pais)

    class Meta:
        model = Alumno
        fields = [
            "numero_estudiante",
            "nombre", "apellido_p", "apellido_m",
            "curp",
            "email", "email_institucional",
            "telefono",
            "pais", "estado",
            "informacionEscolar",
            "sexo", "fecha_nacimiento",
        ]
        widgets = {
            "sexo": forms.Select(attrs={"class": "selectpicker", "data-style": "select-with-transition"}),
            "pais": forms.Select(attrs={"class": "selectpicker", "data-style": "select-with-transition"}),
            "estado": forms.Select(attrs={"class": "selectpicker", "data-style": "select-with-transition"}),
            "informacionEscolar": forms.Select(attrs={"class": "selectpicker", "data-style": "select-with-transition"}),
            "telefono": forms.TextInput(attrs={"type": "tel", "inputmode": "tel"}),
            "curp": forms.TextInput(attrs={"style": "text-transform:uppercase"}),
            "email_institucional": forms.EmailInput(),
        }

    REQUIRED_ON_CREATE = ("curp", "nombre", "apellido_p", "apellido_m")

    def __init__(self, *args, request=None, crear=False, **kwargs):
        """
        crear=True  -> oculta numero_estudiante y no lo requiere (lo asigna servidor).
        crear=False -> en edición, numero_estudiante deshabilitado.
        """
        super().__init__(*args, **kwargs)
        self.request = request

        # En creación: obligatorios
        if crear:
            for name in self.REQUIRED_ON_CREATE:
                if name in self.fields:
                    self.fields[name].required = True
                    self.fields[name].widget.attrs["required"] = "required"
                    self.fields[name].widget.attrs.setdefault("aria-required", "true")

        # Etiqueta con bandera en País
        if "pais" in self.fields:
            self.fields["pais"].label_from_instance = AlumnoForm._pais_label

        # Clase form-control a todos (sin romper checkbox)
        for f in self.fields.values():
            css = f.widget.attrs.get("class", "")
            f.widget.attrs["class"] = (css + " form-control").strip()

        # En edición: bloquear número
        if self.instance and self.instance.pk and "numero_estudiante" in self.fields:
            self.fields["numero_estudiante"].disabled = True

        # En creación: ocultar número
        if crear and "numero_estudiante" in self.fields:
            self.fields["numero_estudiante"].required = False
            self.fields["numero_estudiante"].widget = forms.HiddenInput()

        # Uppercase CURP
        if "curp" in self.fields:
            self.fields["curp"].widget.attrs["oninput"] = "this.value=this.value.toUpperCase()"

        # Estados dependientes
        if "estado" in self.fields:
            self.fields["estado"].queryset = Estado.objects.none()
            if "pais" in self.data:
                try:
                    pais_id = int(self.data.get("pais"))
                except (TypeError, ValueError):
                    pais_id = None
                if pais_id:
                    self.fields["estado"].queryset = Estado.objects.filter(pais_id=pais_id).order_by("nombre")
            elif self.instance.pk and self.instance.pais_id:
                self.fields["estado"].queryset = Estado.objects.filter(pais_id=self.instance.pais_id).order_by("nombre")

        # Planes disponibles (libres o el actual)
        if "informacionEscolar" in self.fields:
            qs = InformacionEscolar.objects.filter(alumno__isnull=True)
            if self.instance and self.instance.pk and self.instance.informacionEscolar_id:
                qs = InformacionEscolar.objects.filter(
                    Q(alumno__isnull=True) | Q(pk=self.instance.informacionEscolar_id)
                )
            self.fields["informacionEscolar"].queryset = qs.order_by("-creado_en")

    def clean_curp(self):
        curp = (self.cleaned_data.get("curp") or "").strip().upper()
        return curp or None

    def save(self, commit=True):
        obj = super().save(commit=False)
        if not obj.pk and self.request and self.request.user.is_authenticated:
            obj.created_by = self.request.user
        if commit:
            obj.save()
        return obj


# ============================================================
#  INFORMACION ESCOLAR
# ============================================================
from alumnos.permisos import (
    user_can_edit_estatus_academico,
    user_can_edit_estatus_administrativo,
)

class InformacionEscolarForm(forms.ModelForm):
    inicio_programa = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        input_formats=["%Y-%m-%d"],
        label="Inicio del programa",
    )
    fin_programa = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        input_formats=["%Y-%m-%d"],
        label="Fin del programa",
    )

    class Meta:
        model = InformacionEscolar
        fields = [
            "programa",
            "financiamiento",
            # Precios
            "precio_colegiatura",
            "monto_descuento",
            "precio_final",
            "meses_programa",
            "precio_inscripcion",
            "precio_reinscripcion",    
            "precio_titulacion",
            "precio_equivalencia",
            "numero_reinscripciones",
            # Resto
            "sede",
            "inicio_programa",
            "fin_programa",
            "grupo",
            "modalidad",
            "matricula",
            "estatus_academico",
            "estatus_administrativo",
            "requiere_datos_de_facturacion",
        ]
        widgets = {
            "programa": forms.Select(attrs={"class": "selectpicker", "data-style": "select-with-transition"}),
            "financiamiento": forms.Select(attrs={"class": "selectpicker", "data-style": "select-with-transition"}),
            "modalidad": forms.Select(attrs={"class": "selectpicker", "data-style": "select-with-transition"}),
            "sede": forms.Select(attrs={"class": "selectpicker", "data-style": "select-with-transition"}),
            "estatus_academico": forms.Select(attrs={"class": "selectpicker", "data-style": "select-with-transition"}),
            "estatus_administrativo": forms.Select(attrs={"class": "selectpicker", "data-style": "select-with-transition"}),
            "requiere_datos_de_facturacion": forms.CheckboxInput(),

            
            "monto_descuento": forms.NumberInput(attrs={"class": "form-control is-readonly-input is-readonly",  "readonly": "readonly", "step": "0.01"}),
            "precio_final": forms.NumberInput(attrs={"class": "form-control is-readonly-input is-readonly",  "readonly": "readonly", "step": "0.01"}),
            "meses_programa": forms.NumberInput(attrs={"class": "form-control is-readonly-input is-readonly",  "readonly": "readonly", "step": "0.01"}),
            "precio_colegiatura": forms.NumberInput(attrs={"class": "form-control is-readonly-input is-readonly",  "readonly": "readonly", "step": "0.01"}),
            # models.py
            "precio_inscripcion": forms.NumberInput(attrs={"class": "form-control is-readonly-input is-readonly",  "readonly": "readonly", "step": "0.01"}),
            "precio_reinscripcion": forms.NumberInput(attrs={"class": "form-control is-readonly-input is-readonly",  "readonly": "readonly", "step": "0.01"}),
            "precio_titulacion": forms.NumberInput(attrs={"class": "form-control is-readonly-input is-readonly",  "readonly": "readonly", "step": "0.01"}),
            "precio_equivalencia": forms.NumberInput(attrs={"class": "form-control is-readonly-input is-readonly",  "readonly": "readonly", "step": "0.01"}),
            "numero_reinscripciones": forms.NumberInput(attrs={"class": "form-control is-readonly-input is-readonly",  "readonly": "readonly"}),

        }

    READONLY_PRICE_FIELDS = [
        
        "monto_descuento",
        "precio_colegiatura",
        "precio_final",
        "meses_programa",
        "precio_inscripcion",
        "precio_reinscripcion",   # <-- añadido para consistencia visual
        "precio_titulacion",
        "precio_equivalencia",
        "numero_reinscripciones",
    ]

    def __init__(self, *args, request=None, readonly_prices=True, **kwargs):
        super().__init__(*args, **kwargs)
        self.request = request
        self._user = getattr(request, "user", None)

        # En GET puedes querer solo-lectura visual; en POST NO se debe bloquear el guardado.
        self._readonly_prices = bool(readonly_prices)
        if self.is_bound:
            for name in [
                "precio_inscripcion",
                "precio_reinscripcion",  # ⬅️ asegúrate de incluirlo
                "precio_titulacion",
                "precio_equivalencia",
                "monto_descuento",
            ]:
                if name in self.fields:
                    self.fields[name].required = False

        # Estética / clases
        for name, field in self.fields.items():
            if isinstance(field.widget, forms.CheckboxInput):
                css = field.widget.attrs.get("class", "")
                field.widget.attrs["class"] = (css + " form-check-input").strip()
            else:
                css = field.widget.attrs.get("class", "")
                field.widget.attrs["class"] = (css + " form-control").strip()

        # Etiqueta de programa
        if "programa" in self.fields:
            self.fields["programa"].label_from_instance = (
                lambda p: f"{getattr(p, 'codigo', '')} — {p.nombre}"
            )

        # Solo-lectura VISUAL cuando aplica (GET)
        if self._readonly_prices:
            for name in self.READONLY_PRICE_FIELDS:
                if name in self.fields:
                    self.fields[name].widget.attrs["readonly"] = "readonly"
                    self.fields[name].widget.attrs.setdefault("tabindex", "-1")
                    css = self.fields[name].widget.attrs.get("class", "")
                    self.fields[name].widget.attrs["class"] = (css + " is-readonly").strip()

        # Permisos de estatus
        can_acad = user_can_edit_estatus_academico(self._user) if self._user else False
        can_admin = user_can_edit_estatus_administrativo(self._user) if self._user else False
        if "estatus_academico" in self.fields and not can_acad:
            self.fields["estatus_academico"].disabled = True
        if "estatus_administrativo" in self.fields and not can_admin:
            self.fields["estatus_administrativo"].disabled = True

    def clean(self):
        cleaned = super().clean()

        # Asegurar defaults seguros si el template no envía algún precio
        for name, default in [
            ("precio_inscripcion", Decimal("0.00")),
            ("precio_reinscripcion", Decimal("0.00")),
            ("precio_titulacion", Decimal("0.00")),
            ("precio_equivalencia", Decimal("0.00")),
            ("monto_descuento", Decimal("0.00")),
        ]:
            if cleaned.get(name) in (None, ""):
                cleaned[name] = default

        # Recalcular precio_final simple (colegiatura - descuento)
        coleg = cleaned.get("precio_colegiatura") or Decimal("0.00")
        desc = cleaned.get("monto_descuento") or Decimal("0.00")
        final = cleaned.get("precio_final")
        try:
            esperado = coleg - desc
            if final is None or final != esperado:
                cleaned["precio_final"] = esperado
        except Exception:
            pass

        # Refuerzo de permisos de estatus
        if self.instance and self.instance.pk:
            can_acad = user_can_edit_estatus_academico(self._user) if self._user else False
            can_admin = user_can_edit_estatus_administrativo(self._user) if self._user else False
            if "estatus_academico" in cleaned and not can_acad:
                cleaned["estatus_academico"] = self.instance.estatus_academico
            if "estatus_administrativo" in cleaned and not can_admin:
                cleaned["estatus_administrativo"] = self.instance.estatus_administrativo

        return cleaned

    def save(self, commit=True):
        obj = super().save(commit=False)

        if self.instance and self.instance.pk:
            # Permisos de estatus (no tocar si no puede)
            can_acad = user_can_edit_estatus_academico(self._user) if self._user else False
            can_admin = user_can_edit_estatus_administrativo(self._user) if self._user else False
            if not can_acad:
                obj.estatus_academico = self.instance.estatus_academico
            if not can_admin:
                obj.estatus_administrativo = self.instance.estatus_administrativo

            # En GET (_readonly_prices=True) no pisamos precios con datos del form
            # (en POST __init__ ya fuerza _readonly_prices=False)
            if self._readonly_prices:
                for name in self.READONLY_PRICE_FIELDS:
                    if hasattr(self.instance, name):
                        setattr(obj, name, getattr(self.instance, name))

        if commit:
            obj.save()
        return obj

# ============================================================
#  DOCUMENTOS (nuevo esquema)
# ============================================================

def _es_extranjero(info: InformacionEscolar) -> bool:
    """
    Heurística sencilla: extranjero si el alumno tiene país y no es MX.
    Si no hay alumno/país, no filtramos por nacionalidad (tratamos como 'todos').
    """
    if not info:
        return False
    alumno = getattr(info, "alumno", None)
    if not alumno or not alumno.pais:
        return False
    iso2 = (alumno.pais.codigo_iso2 or "").upper()
    return bool(iso2 and iso2 != "MX")


class DocumentoAlumnoCreateForm(forms.ModelForm):
    """
    Para subir un documento (tipo + archivo) a un plan (info_escolar).
    La vista debe pasar info_escolar=<obj> en __init__ o setear instance.info_escolar.
    """
    archivo = forms.FileField(widget=ClearableFileInputAccept())

    class Meta:
        model = DocumentoAlumno
        fields = ["tipo", "archivo"]
        widgets = {
            "tipo": forms.Select(attrs={"class": "selectpicker", "data-style": "select-with-transition" }),
        }

    def __init__(self, *args, info_escolar: InformacionEscolar = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.info_escolar = info_escolar or getattr(self.instance, "info_escolar", None)

        # Añade clase form-control SOLO a no-file widgets
        for f in self.fields.values():
            w = f.widget
            if isinstance(w, (forms.FileInput, forms.ClearableFileInput)):
                # El widget de archivo ya trae 'form-control-file'
                continue
            css = w.attrs.get("class", "")
            w.attrs["class"] = (css + " form-control").strip()

        # Filtrar tipos por requisitos del programa y por nacionalidad (aplica_a)
        tipos_qs = DocumentoTipo.objects.filter(activo=True)
        if self.info_escolar and self.info_escolar.programa_id:
            reqs = ProgramaDocumentoRequisito.objects.filter(
                programa=self.info_escolar.programa, activo=True, tipo__activo=True
            ).select_related("tipo")

            # Filtrado por nacionalidad
            es_ext = _es_extranjero(self.info_escolar)
            if es_ext:
                reqs = reqs.filter(Q(aplica_a="todos") | Q(aplica_a="solo_extranjeros"))
            else:
                reqs = reqs.filter(Q(aplica_a="todos") | Q(aplica_a="solo_nacionales"))

            tipos_qs = DocumentoTipo.objects.filter(id__in=reqs.values_list("tipo_id", flat=True))

        if "tipo" in self.fields:
            self.fields["tipo"].queryset = tipos_qs.order_by("nombre")
            self.fields["tipo"].label_from_instance = lambda t: f"{t.nombre}"

    def clean(self):
        cleaned = super().clean()
        tipo = cleaned.get("tipo")
        if not self.info_escolar:
            raise forms.ValidationError("Falta el plan (info_escolar) para adjuntar el documento.")

        if not tipo:
            return cleaned

        # Validar contra max/min del requisito correspondiente
        req = ProgramaDocumentoRequisito.objects.filter(
            programa=self.info_escolar.programa_id,
            tipo=tipo,
            activo=True
        ).first()

        if req:
            # ¿cuántos ya subidos de este tipo?
            count_actual = DocumentoAlumno.objects.filter(info_escolar=self.info_escolar, tipo=tipo).count()
            # Vamos a agregar 1 (este) => validar máximo
            if not tipo.multiple and count_actual >= 1:
                raise forms.ValidationError(f"El tipo '{tipo.nombre}' no permite múltiples archivos.")
            if req.maximo and count_actual + 1 > req.maximo:
                raise forms.ValidationError(f"Máximo permitido para '{tipo.nombre}': {req.maximo} archivo(s).")

        return cleaned

    def save(self, commit=True):
        obj = super().save(commit=False)
        if self.info_escolar:
            obj.info_escolar = self.info_escolar
        if commit:
            obj.save()
        return obj


class DocumentoAlumnoUpdateForm(forms.ModelForm):
    """
    Para editar un documento existente (solo cambiar archivo/notas/validez).
    """
    archivo = forms.FileField(required=False, widget=ClearableFileInputAccept())

    class Meta:
        model = DocumentoAlumno
        fields = ["archivo", "valido", "notas"]

  

 

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.fields.values():
            w = f.widget
            # No pises el file input
            if isinstance(w, (forms.FileInput, forms.ClearableFileInput)):
                continue
            css = w.attrs.get("class", "")
            w.attrs["class"] = (css + " form-control").strip()


# Opcionales: formsets para manejar varios documentos en una sola pantalla
DocumentoAlumnoFormSet = modelformset_factory(
    DocumentoAlumno,
    form=DocumentoAlumnoUpdateForm,
    extra=0,
    can_delete=True,
)

DocumentoInlineFormSet = inlineformset_factory(
    InformacionEscolar,
    DocumentoAlumno,
    form=DocumentoAlumnoUpdateForm,
    extra=0,
    can_delete=True,
)
