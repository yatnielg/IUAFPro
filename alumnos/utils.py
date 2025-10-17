# alumnos/utils.py
from django.db import transaction
from .models import ContadorAlumno

def siguiente_numero_estudiante():
    """
    Devuelve el siguiente número de estudiante de forma transaccional
    y segura para concurrencia.
    """
    with transaction.atomic():
        contador, _ = (ContadorAlumno.objects
                       .select_for_update()
                       .get_or_create(llave="global"))
        contador.ultimo_numero = (contador.ultimo_numero or 0) + 1
        contador.save(update_fields=["ultimo_numero"])
        return contador.ultimo_numero
