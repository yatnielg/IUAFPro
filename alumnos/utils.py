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

###############################################################
from .models import ClipCredential
from django.core.exceptions import ObjectDoesNotExist

def get_active_clip_credential(sandbox=None):
    """
    Retorna la credencial activa.
    Si sandbox es True/False lo filtra; si es None busca la activa por defecto.
    Lanza None si no existe.
    """
    qs = ClipCredential.objects.all()
    if sandbox is True:
        qs = qs.filter(is_sandbox=True)
    elif sandbox is False:
        qs = qs.filter(is_sandbox=False)

    try:
        # preferimos la que tenga active=True
        cred = qs.filter(active=True).first()
        if not cred:
            cred = qs.first()
        return cred
    except ObjectDoesNotExist:
        return None
