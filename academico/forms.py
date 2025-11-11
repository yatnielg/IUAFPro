# academico/forms.py
from django import forms
from .models import Calificacion

class CalificacionForm(forms.ModelForm):
    """
    Form para capturar calificaciones:
    - Acepta coma o punto como separador decimal.
    - Permite dejar la nota vacía (None).
    - Valida rango 0..100.
    - Aplica estilos de Bootstrap a inputs
      y estilos de 'selectpicker' automáticamente a cualquier Select/SelectMultiple.
    """
    class Meta:
        model = Calificacion
        fields = ("nota", "observaciones")
        widgets = {
            "nota": forms.NumberInput(
                attrs={
                    "step": "0.01",
                    "min": "0",
                    "max": "100",
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
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Aplica selectpicker a todos los selects del form (por si agregas 'programa', etc.)
        for name, field in self.fields.items():
            widget = field.widget
            if isinstance(widget, (forms.Select, forms.SelectMultiple)):
                # Conserva clases existentes y añade selectpicker
                base_class = widget.attrs.get("class", "")
                widget.attrs["class"] = (base_class + " selectpicker").strip()
                widget.attrs.setdefault("data-style", "select-with-transition")
                widget.attrs.setdefault("data-size", "5")  # opcional

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
                    "La nota debe ser numérica (usa 80.5 o 80,5)."
                )
        if v is None:
            return None
        if v < 0 or v > 100:
            raise forms.ValidationError("La nota debe estar entre 0 y 100.")
        return v


# Formset listo para la vista (sin extra, sin delete)
CalificacionFormSet = forms.modelformset_factory(
    Calificacion,
    form=CalificacionForm,
    fields=("nota", "observaciones"),
    extra=0,
    can_delete=False,
)
