# academico/forms.py
from django import forms
from .models import Calificacion, Profesor


class CalificacionForm(forms.ModelForm):
    class Meta:
        model = Calificacion
        fields = ("nota", "observaciones", "profesor", "fecha")
        widgets = {
            "nota": forms.NumberInput(
                attrs={
                    "step": "0.01",
                    "min": "0",
                    "max": "10",
                    "inputmode": "decimal",
                    "class": "form-control text-end",
                }
            ),
            "observaciones": forms.Textarea(
                attrs={
                    "rows": 1,
                    "class": "form-control",
                }
            ),
            "profesor": forms.Select(
                attrs={
                    "class": "form-control",
                }
            ),
            "fecha": forms.DateInput(
                format="%Y-%m-%d",     # 👈 IMPORTANTE: formato HTML5
                attrs={
                    "type": "date",
                    "class": "form-control",
                }
            ),
        }

        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Solo profesores activos
        self.fields["profesor"].queryset = Profesor.objects.filter(activo=True)

        # Aseguramos formatos que acepta el campo fecha
        self.fields["fecha"].input_formats = ["%Y-%m-%d", "%d/%m/%Y"]

        # Aplica selectpicker a todos los selects
        for name, field in self.fields.items():
            widget = field.widget
            if isinstance(widget, (forms.Select, forms.SelectMultiple)):
                base_class = widget.attrs.get("class", "")
                widget.attrs["class"] = (base_class + " selectpicker").strip()
                widget.attrs.setdefault("data-style", "select-with-transition")
                widget.attrs.setdefault("data-size", "5")



    def clean_nota(self):
        v = self.cleaned_data.get("nota")
        # Si llega como string por localización/navegador, permitir coma decimal
        if isinstance(v, str):
            s = v.strip().replace(",", ".")
            if s == "":
                return None
            try:
                v = float(s)
            except Exception:
                raise forms.ValidationError(
                    "La nota debe ser numérica (usa 8.5 o 8,5)."
                )
        if v is None:
            return None
        if v < 0 or v > 10:
            raise forms.ValidationError("La nota debe estar entre 0 y 10.")
        return v


# Formset listo para la vista (sin extra, sin delete)
# academico/forms.py
CalificacionFormSet = forms.modelformset_factory(
    Calificacion,
    form=CalificacionForm,
    fields=("nota", "observaciones", "profesor", "fecha"),
    extra=0,
    can_delete=False,
)

