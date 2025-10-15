# forms.py
from django import forms
from .models import (
    Alumno, Estado, Pais, Sede,
    InformacionEscolar, Programa,
    DocumentosAlumno,
)

# ---------- Widgets helpers ----------
class ClearableFileInputAccept(forms.ClearableFileInput):
    """File input que por defecto acepta PDF/JPG/PNG."""
    def __init__(self, *args, **kwargs):
        attrs = kwargs.setdefault("attrs", {})
        attrs.setdefault("accept", ".pdf,.png,.jpg,.jpeg")
        super().__init__(*args, **kwargs)


# =========================================
#               ALUMNO
# =========================================
class AlumnoForm(forms.ModelForm):
    # Fuerza widget HTML5 y el formato ISO que los <input type="date"> esperan
    fecha_nacimiento = forms.DateField(
        required=False,
        widget=forms.DateInput(
            attrs={'type': 'date'},
            format='%Y-%m-%d',
        ),
        input_formats=['%Y-%m-%d'],  # para bind/validación
    )

    @staticmethod
    def _pais_label(pais: Pais) -> str:
        # Usa el __str__ de Pais (ya incluye bandera) o construye aquí:
        return str(pais)

    class Meta:
        model = Alumno
        fields = [
            "numero_estudiante",
            "nombre", "apellido_p", "apellido_m",
            "curp", "email", "telefono",
            "pais", "estado",
            "informacionEscolar",     # <-- único campo de plan en Alumno
            "sexo", "fecha_nacimiento",
        ]
        widgets = {
            "sexo": forms.Select(attrs={"class": "selectpicker", "data-style": "select-with-transition"}),
            "pais": forms.Select(attrs={"class": "selectpicker", "data-style": "select-with-transition"}),
            "estado": forms.Select(attrs={"class": "selectpicker", "data-style": "select-with-transition"}),
            "informacionEscolar": forms.Select(attrs={"class": "selectpicker", "data-style": "select-with-transition"}),
            "telefono": forms.TextInput(attrs={"type": "tel", "inputmode": "tel"}),
            "curp": forms.TextInput(attrs={"style": "text-transform:uppercase"}),
        }

    def __init__(self, *args, request=None, **kwargs):
        super().__init__(*args, **kwargs)

        # Etiquetas de país con bandera (opcional)
        if "pais" in self.fields:
            self.fields["pais"].label_from_instance = AlumnoForm._pais_label

        # form-control a todo (no afecta selectpicker)
        for f in self.fields.values():
            css = f.widget.attrs.get("class", "")
            f.widget.attrs["class"] = (css + " form-control").strip()

        # Bloquear PK en edición
        if self.instance and self.instance.pk:
            self.fields["numero_estudiante"].disabled = True

        # CURP uppercase visual
        if "curp" in self.fields:
            self.fields["curp"].widget.attrs["oninput"] = "this.value=this.value.toUpperCase()"

        # Encadenar estados por país
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

        # Mostrar solo planes libres (o el plan actual del alumno)
        if "informacionEscolar" in self.fields:
            from django.db.models import Q
            qs = InformacionEscolar.objects.filter(alumno__isnull=True)
            if self.instance and self.instance.pk and self.instance.informacionEscolar_id:
                qs = InformacionEscolar.objects.filter(
                    Q(alumno__isnull=True) | Q(pk=self.instance.informacionEscolar_id)
                )
            self.fields["informacionEscolar"].queryset = qs.order_by("-creado_en")

    def clean_curp(self):
        curp = (self.cleaned_data.get("curp") or "").strip().upper()
        return curp or None


# =========================================
#       INFORMACION ESCOLAR (Plan)
# =========================================
class InformacionEscolarForm(forms.ModelForm):
    fin_programa = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))

    class Meta:
        model = InformacionEscolar
        fields = [
            "programa",
            "financiamiento",
            "precio_colegiatura",
            "monto_descuento",
            "meses_programa",
            "precio_inscripcion",
            "precio_titulacion",
            "precio_equivalencia",
            "numero_reinscripciones",
            "precio_final",
            "fin_programa",
            "grupo",
            "modalidad",
            "matricula",
            "estatus_academico",
            "estatus_administrativo",
        ]
        widgets = {
            "programa": forms.Select(attrs={"class": "selectpicker", "data-style": "select-with-transition"}),
            "financiamiento": forms.Select(attrs={"class": "selectpicker", "data-style": "select-with-transition"}),
            "modalidad": forms.Select(attrs={"class": "selectpicker", "data-style": "select-with-transition"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # form-control a todo
        for f in self.fields.values():
            css = f.widget.attrs.get("class", "")
            f.widget.attrs["class"] = (css + " form-control").strip()
        # etiqueta de programa más clara
        self.fields["programa"].label_from_instance = lambda p: f"{p.codigo} — {p.nombre}"


# =========================================
#        DOCUMENTOS DEL ALUMNO
# =========================================
class DocumentosAlumnoForm(forms.ModelForm):
    class Meta:
        model = DocumentosAlumno
        fields = [
            "acta_nacimiento",
            "curp",
            "certificado_estudios",
            "titulo_grado",
            "solicitud_registro",
            "validacion_autenticidad",
            "carta_compromiso",
            "carta_interes",
            "identificacion_oficial",
            "otro_documento",
        ]
        widgets = {
            "acta_nacimiento": ClearableFileInputAccept,
            "curp": ClearableFileInputAccept,
            "certificado_estudios": ClearableFileInputAccept,
            "titulo_grado": ClearableFileInputAccept,
            "solicitud_registro": ClearableFileInputAccept,
            "validacion_autenticidad": ClearableFileInputAccept,
            "carta_compromiso": ClearableFileInputAccept,
            "carta_interes": ClearableFileInputAccept,
            "identificacion_oficial": ClearableFileInputAccept,
            "otro_documento": ClearableFileInputAccept,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.fields.values():
            css = f.widget.attrs.get("class", "")
            f.widget.attrs["class"] = (css + " form-control").strip()
