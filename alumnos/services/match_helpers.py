# alumnos/services/match_helpers.py

import unicodedata
import re
from typing import List

from django.db.models import Q, Value
from django.db.models.functions import Concat, Lower, Coalesce
from django.core.exceptions import FieldDoesNotExist

from alumnos.models import Alumno

def _norm(s: str) -> str:
    s = (s or "").strip().lower()
    s = unicodedata.normalize('NFKD', s)
    return ''.join(c for c in s if not unicodedata.combining(c))

def _compact(s: str) -> str:
    return " ".join((s or "").split())

# ===== Lista negra =====
BLACKLIST_EXACT = {
    "payclip s de rl de cv",
    "por identificar",  # <= normaliza a minúsculas
}
BLACKLIST_SUBSTR = [
    "deposito referenciado",
    "spei interbancario",
    "por identificar",
]
BLACKLIST_REGEX = [
    re.compile(r"\bpayclip\b.*\bs de rl de cv\b"),
]

def _is_blacklisted(texto: str) -> bool:
    t = _compact(_norm(texto or ""))
    if not t:
        return False
    if t in BLACKLIST_EXACT:
        return True
    for frag in BLACKLIST_SUBSTR:
        if frag in t and len(frag) >= 5:
            return True
    for rx in BLACKLIST_REGEX:
        if rx.search(t):
            return True
    return False

def _build_q_for_term(t_raw: str, t_norm: str, parts: List[str]) -> Q:
    """
    Construye un Q() para un solo término de búsqueda (ya normalizado/compactado).
    - t_raw: versión compactada sin normalizar (para emails/curp/teléfono).
    - t_norm: versión normalizada y compactada para nombres.
    - parts: t_norm.split()
    """
    q = (
        Q(email__icontains=t_raw) |
        Q(email_institucional__icontains=t_raw) |
        Q(curp__icontains=t_raw) |
        Q(telefono__icontains=t_raw)
    )

    # Si Alumno tuviera 'nombre_detectado_save', intenta usarlo también
    try:
        Alumno._meta.get_field("nombre_detectado_save")
        q |= Q(nombre_detectado_save__icontains=t_raw) | Q(nombre_detectado_save__icontains=t_norm)
    except FieldDoesNotExist:
        pass

    if len(parts) >= 3:
        t3 = " ".join(parts)
        q |= Q(full_name__icontains=t3) | Q(full_name_rev__icontains=t3)
        q |= Q(nombre_ap__icontains=" ".join(parts[:2])) | Q(ap_nombre__icontains=" ".join(parts[1:3]))
    elif len(parts) == 2:
        t2 = " ".join(parts)
        p0, p1 = parts
        q |= (Q(nombre_ap__icontains=t2) |
              Q(ap_nombre__icontains=t2) |
              Q(full_name__icontains=t2) |
              Q(full_name_rev__icontains=t2))
        q |= (Q(nombre__icontains=p0) & (Q(apellido_p__icontains=p1) | Q(apellido_m__icontains=p1)))
        q |= (Q(apellido_p__icontains=p0) & Q(nombre__icontains=p1))
    elif len(parts) == 1:
        p0 = parts[0]
        q |= Q(nombre__icontains=p0) | Q(apellido_p__icontains=p0) | Q(apellido_m__icontains=p0)

    return q

def buscar_alumnos_candidatos(texto: str, limit: int = 20):
    """
    Devuelve queryset de alumnos que 'suena' a `texto`, incluyendo:
    - match por nombre completo y combinaciones
    - soporte para múltiplos términos separados por coma (",")
      p.ej: "juan perez, maria lopez"
    - lista negra para evitar falsos positivos
    """
    if _is_blacklisted(texto):
        return Alumno.objects.none()

    # Divide por coma para soportar varios nombres en una sola cadena
    # Ej: "juan perez, maria lopez" => ["juan perez", "maria lopez"]
    #raw_terms = [seg for seg in (texto or "").split(",") if seg and seg.strip()]
    raw_terms = re.split(r"[,\;|]+", texto or "")

    if not raw_terms:
        return Alumno.objects.none()

    base = (
        Alumno.objects
        .annotate(
            full_name=Lower(Concat(
                Coalesce('nombre', Value('')), Value(' '),
                Coalesce('apellido_p', Value('')), Value(' '),
                Coalesce('apellido_m', Value(''))
            )),
            full_name_rev=Lower(Concat(
                Coalesce('apellido_p', Value('')), Value(' '),
                Coalesce('apellido_m', Value('')), Value(' '),
                Coalesce('nombre', Value(''))
            )),
            nombre_ap=Lower(Concat(
                Coalesce('nombre', Value('')), Value(' '),
                Coalesce('apellido_p', Value(''))
            )),
            ap_nombre=Lower(Concat(
                Coalesce('apellido_p', Value('')), Value(' '),
                Coalesce('nombre', Value(''))
            )),
        )
        .only('numero_estudiante','nombre','apellido_p','apellido_m','email','curp','telefono')
    )

    # Para cada término (separado por coma) construimos su propio Q y combinamos con OR
    q_total = Q()
    for term in raw_terms:
        t_raw = _compact(term or "")
        t_norm = _compact(_norm(term or ""))
        if not t_norm:
            continue
        parts = t_norm.split()
        q_total |= _build_q_for_term(t_raw, t_norm, parts)

    if not q_total:
        return Alumno.objects.none()

    # distinct() por si un alumno matchea con más de un término
    return base.filter(q_total).distinct()[:limit]
