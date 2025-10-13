# forms.py
from django import forms
from .models import Alumno

""" class AlumnoForm(forms.ModelForm):
    class Meta:
        model = Alumno
        fields = [
            "numero_estudiante", "nombre", "apellido_p", "apellido_m",
            "curp", "email", "telefono",
            "pais", "estado",
            "programa", "estatus_administrativo", "estatus_academico",
            "estatus", "sexo", "fecha_nacimiento"
        ]
        widgets = {
            "fecha_nacimiento": forms.DateInput(attrs={"type": "date"}),
            "sexo": forms.Select(attrs={
                'class': 'selectpicker', 
                'data-style': 'select-with-transition'
            }),
            "pais": forms.Select(),
            "estado": forms.Select(),
            "programa": forms.Select(),
            "email": forms.EmailInput(),
            "telefono": forms.TextInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Añade clases a todos los campos
        for f in self.fields.values():
            existing = f.widget.attrs.get("class", "")
            f.widget.attrs["class"] = (existing + " form-control").strip()

        # El PK no debe cambiar al editar
        if self.instance and self.instance.pk:
            self.fields["numero_estudiante"].disabled = True

    def clean_curp(self):
        curp = (self.cleaned_data.get("curp") or "").strip()
        return curp.upper()

 """

#####################

class AlumnoForm(forms.ModelForm):
    class Meta:
        model = Alumno
        fields = [
            "numero_estudiante", "nombre", "apellido_p", "apellido_m",
            "curp", "email", "telefono",
            "pais", "estado",
            "programa", "estatus_administrativo", "estatus_academico",
            "estatus", "sexo", "fecha_nacimiento"
        ]
        widgets = {
            "fecha_nacimiento": forms.DateInput(attrs={"type": "date"}),
            "sexo": forms.Select(attrs={'class': 'selectpicker', 'data-style': 'select-with-transition'}),
            "pais": forms.Select(attrs={'class': 'selectpicker', 'data-style': 'select-with-transition'}),
            "programa": forms.Select(attrs={'class': 'selectpicker', 'data-style': 'select-with-transition'}),
            "estado": forms.Select(attrs={'class': 'selectpicker', 'data-style': 'select-with-transition'}),
                            
            
            }

    def __init__(self, *args, request=None, **kwargs):
        # request es OPCIONAL y viene por keyword
        self.request = request
        super().__init__(*args, **kwargs)

        # estilos
        for f in self.fields.values():
            css = f.widget.attrs.get("class", "")
            f.widget.attrs["class"] = (css + " form-control").strip()

        # si estás editando, bloquea el PK
        if self.instance and self.instance.pk:
            self.fields["numero_estudiante"].disabled = True

        # si necesitas filtrar choices por usuario:
        # if self.request and self.request.user.is_staff:
        #     self.fields["programa"].queryset = Programa.objects.all()