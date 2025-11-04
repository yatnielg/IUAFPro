# alumnos/services/documentos_helpers.py
from alumnos.models import ProgramaDocumentoRequisito

def requisitos_para_alumno(programa, alumno):
    """
    Devuelve los requisitos documentales que aplican al alumno, filtrando por nacionales/extranjeros.
    Considera alumno.pais (ISO2 o nombre) para determinar si es nacional (MX) o extranjero.
    """
    if not programa:
        return ProgramaDocumentoRequisito.objects.none()

    # Ajusta esta lógica si tu definición de "nacional" difiere
    es_nacional = False
    try:
        if alumno and alumno.pais and (alumno.pais.codigo_iso2 or "").upper() == "MX":
            es_nacional = True
    except Exception:
        pass

    qs = ProgramaDocumentoRequisito.objects.filter(programa=programa, activo=True)

    if es_nacional:
        qs = qs.exclude(aplica_a="solo_extranjeros")
    else:
        qs = qs.exclude(aplica_a="solo_nacionales")

    return qs.select_related("tipo")
