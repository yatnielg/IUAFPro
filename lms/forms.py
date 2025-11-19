# lms/forms.py
from django import forms
from .models import Entrega


class EntregaForm(forms.ModelForm):
    """
    Form para subir/editar una entrega de actividad tipo 'tarea'.
    """
    class Meta:
        model = Entrega
        fields = ["archivo", "texto_respuesta"]
        widgets = {
            "archivo": forms.ClearableFileInput(
                attrs={
                    "class": "form-control",
                }
            ),
            "texto_respuesta": forms.Textarea(
                attrs={
                    "rows": 4,
                    "class": "form-control",
                    "placeholder": "Escribe tu respuesta aquí…",
                }
            ),
        }


class QuizForm(forms.Form):
    """
    Form dinámico: genera un campo por cada Pregunta de la Actividad.
    - opcion_multiple -> radios
    - abierta         -> textarea
    """

    def __init__(self, *args, actividad=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.actividad = actividad
        if not actividad:
            return

        for pregunta in actividad.preguntas.all():
            field_name = f"pregunta_{pregunta.id}"

            if pregunta.tipo == "opcion_multiple":
                # Opciones como radio buttons
                choices = [
                    (op.id, op.texto)
                    for op in pregunta.opciones.all()
                ]
                self.fields[field_name] = forms.ChoiceField(
                    label=pregunta.texto,
                    choices=choices,
                    widget=forms.RadioSelect(
                        attrs={
                            # esta clase va en el <ul> que envuelve a los <li>
                            "class": "quiz-options",
                        }
                    ),
                    required=True,
                )
            else:
                # Respuesta abierta
                self.fields[field_name] = forms.CharField(
                    label=pregunta.texto,
                    widget=forms.Textarea(
                        attrs={
                            "rows": 2,
                            "class": "form-control",
                            "placeholder": "Escribe tu respuesta…",
                        }
                    ),
                    required=True,
                )
