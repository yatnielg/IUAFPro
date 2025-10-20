# forms.py
from django import forms
from django.db.models import Q

from .models import (
    Alumno, Estado, Pais,
    InformacionEscolar, DocumentosAlumno,
)

# ---------- Widgets helpers ----------
class ClearableFileInputAccept(forms.ClearableFileInput):
    def __init__(self, *args, **kwargs):
        attrs = kwargs.setdefault("attrs", {})
        attrs.setdefault("accept", ".pdf,.png,.jpg,.jpeg")
        super().__init__(*args, **kwargs)


# ============ ALUMNO ============
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
        crear=True  -> ocultar numero_estudiante y no requerirlo (se asigna en la vista)
        crear=False -> en edición, numero_estudiante deshabilitado
        """
        super().__init__(*args, **kwargs)
        self.request = request

        # En creación: estos campos son obligatorios
        if crear:
            for name in self.REQUIRED_ON_CREATE:
                if name in self.fields:
                    self.fields[name].required = True                 # validación servidor
                    self.fields[name].widget.attrs["required"] = "required"  # validación HTML
                    # opcional UX:
                    self.fields[name].widget.attrs.setdefault("aria-required", "true")

        # Mostrar bandera en etiquetas de país
        if "pais" in self.fields:
            self.fields["pais"].label_from_instance = AlumnoForm._pais_label

        # Agregar clase form-control a todos
        for f in self.fields.values():
            css = f.widget.attrs.get("class", "")
            f.widget.attrs["class"] = (css + " form-control").strip()

        # En edición: no permitir cambiar el número
        if self.instance and self.instance.pk:
            if "numero_estudiante" in self.fields:
                self.fields["numero_estudiante"].disabled = True

        # En creación: ocultar y no requerir el número (lo asigna el servidor)
        if crear:
            if "numero_estudiante" in self.fields:
                self.fields["numero_estudiante"].required = False
                self.fields["numero_estudiante"].widget = forms.HiddenInput()

        # CURP toUppercase en cliente
        if "curp" in self.fields:
            self.fields["curp"].widget.attrs["oninput"] = "this.value=this.value.toUpperCase()"

        # Estados dependientes de país
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

        # Mostrar planes libres o el actual del alumno
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
    

# ============ INFORMACION ESCOLAR ============
from django import forms
from .models import InformacionEscolar
from alumnos.permisos import (
    user_can_edit_estatus_academico,
    user_can_edit_estatus_administrativo,
)

class InformacionEscolarForm(forms.ModelForm):
    # Fechas como <input type="date">
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

            # --- Precios y reinscripciones (solo lectura en UI) ---
            "precio_colegiatura",
            "monto_descuento",
            "precio_final",
            "meses_programa",
            "precio_inscripcion",
            "precio_titulacion",
            "precio_equivalencia",
            "numero_reinscripciones",

            # --- Resto ---
            "sede",
            "inicio_programa",
            "fin_programa",
            "grupo",
            "modalidad",
            "matricula",
            "estatus_academico",
            "estatus_administrativo",

            # Booleano extra
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
        }

    READONLY_PRICE_FIELDS = [
        "precio_colegiatura",
        "monto_descuento",
        "precio_final",
        "meses_programa",
        "precio_inscripcion",
        "precio_titulacion",
        "precio_equivalencia",
        "numero_reinscripciones",
    ]

    def __init__(self, *args, request=None, readonly_prices=True, **kwargs):
        """
        Pásame request=request en la vista para poder chequear grupos.
        readonly_prices=True => pone los campos de precios en solo-lectura (UI) y (opcional) los protege en save().
        """
        super().__init__(*args, **kwargs)
        self.request = request
        self._user = getattr(request, "user", None)
        self._readonly_prices = bool(readonly_prices)

        # Añade clases a widgets (sin romper el checkbox)
        for name, field in self.fields.items():
            if isinstance(field.widget, forms.CheckboxInput):
                css = field.widget.attrs.get("class", "")
                field.widget.attrs["class"] = (css + " form-check-input").strip()
            else:
                css = field.widget.attrs.get("class", "")
                field.widget.attrs["class"] = (css + " form-control").strip()

        # Etiqueta para programa
        if "programa" in self.fields:
            self.fields["programa"].label_from_instance = lambda p: f"{getattr(p, 'codigo', '')} — {p.nombre}"

        # Solo lectura (UI) para precios (no bloquea POST malicioso)
        if self._readonly_prices:
            for name in self.READONLY_PRICE_FIELDS:
                if name in self.fields:
                    self.fields[name].widget.attrs["readonly"] = "readonly"
                    self.fields[name].widget.attrs.setdefault("tabindex", "-1")
                    css = self.fields[name].widget.attrs.get("class", "")
                    self.fields[name].widget.attrs["class"] = (css + " is-readonly").strip()

        # Permisos de estatus
        can_acad  = user_can_edit_estatus_academico(self._user) if self._user else False
        can_admin = user_can_edit_estatus_administrativo(self._user) if self._user else False

        if "estatus_academico" in self.fields and not can_acad:
            self.fields["estatus_academico"].disabled = True

        if "estatus_administrativo" in self.fields and not can_admin:
            self.fields["estatus_administrativo"].disabled = True

    def clean(self):
        cleaned = super().clean()

        # Recalcular precio_final simple (colegiatura - descuento)
        coleg = cleaned.get("precio_colegiatura") or 0
        desc  = cleaned.get("monto_descuento") or 0
        final = cleaned.get("precio_final")
        try:
            if final is None or final != (coleg - desc):
                cleaned["precio_final"] = coleg - desc
        except Exception:
            pass

        # Refuerzo de permisos sobre estatus (en edición)
        if self.instance and self.instance.pk:
            can_acad  = user_can_edit_estatus_academico(self._user) if self._user else False
            can_admin = user_can_edit_estatus_administrativo(self._user) if self._user else False

            if "estatus_academico" in cleaned and not can_acad:
                cleaned["estatus_academico"] = self.instance.estatus_academico

            if "estatus_administrativo" in cleaned and not can_admin:
                cleaned["estatus_administrativo"] = self.instance.estatus_administrativo

        return cleaned

    def save(self, commit=True):
        """
        Protección extra en servidor:
        - Si no puede editar estatus, conserva los valores previos.
        - Si readonly_prices=True y es edición, conserva los campos de precios originales.
        """
        obj = super().save(commit=False)

        if self.instance and self.instance.pk:
            # Permisos de estatus
            can_acad  = user_can_edit_estatus_academico(self._user) if self._user else False
            can_admin = user_can_edit_estatus_administrativo(self._user) if self._user else False

            if not can_acad:
                obj.estatus_academico = self.instance.estatus_academico
            if not can_admin:
                obj.estatus_administrativo = self.instance.estatus_administrativo

            # Protección de precios si marcaste solo-lectura
            if self._readonly_prices:
                for name in self.READONLY_PRICE_FIELDS:
                    if hasattr(self.instance, name):
                        setattr(obj, name, getattr(self.instance, name))

        if commit:
            obj.save()
        return obj


# forms.py
class DocumentosAlumnoForm(forms.ModelForm):
    class Meta:
        model = DocumentosAlumno
        fields = [
            "acta_nacimiento","curp","certificado_estudios","titulo_grado",
            "solicitud_registro","validacion_autenticidad","carta_compromiso",
            "carta_interes","identificacion_oficial","otro_documento",
        ]
        widgets = {
            "acta_nacimiento":        forms.ClearableFileInput(attrs={"accept": ".pdf"}),
            "curp":                   forms.ClearableFileInput(attrs={"accept": ".pdf"}),
            "certificado_estudios":   forms.ClearableFileInput(attrs={"accept": ".pdf"}),
            "titulo_grado":           forms.ClearableFileInput(attrs={"accept": ".pdf"}),
            "solicitud_registro":     forms.ClearableFileInput(attrs={"accept": ".pdf"}),
            "validacion_autenticidad":forms.ClearableFileInput(attrs={"accept": ".pdf"}),
            "carta_compromiso":       forms.ClearableFileInput(attrs={"accept": ".pdf"}),
            "carta_interes":          forms.ClearableFileInput(attrs={"accept": ".pdf"}),
            "identificacion_oficial": forms.ClearableFileInput(attrs={"accept": ".pdf,image/*"}),
            "otro_documento":         forms.ClearableFileInput(attrs={"accept": ".pdf,image/*"}),
        }