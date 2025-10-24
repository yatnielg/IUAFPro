# alumnos/services/match_helpers.py
import unicodedata
from django.db.models import Q
from alumnos.models import Alumno

def _norm(s: str) -> str:
    s = (s or "").strip().lower()
    s = unicodedata.normalize('NFKD', s)
    return ''.join(c for c in s if not unicodedata.combining(c))

def buscar_alumnos_candidatos(texto: str, limit: int = 20):
    """Devuelve queryset de alumnos que 'suena' a `texto`."""
    t = _norm(texto)
    if not t:
        return Alumno.objects.none()

    # separa posibles partes de nombre
    parts = [p for p in t.split() if p]

    q = (
        Q(nombre__icontains=texto) |
        Q(apellido_p__icontains=texto) |
        Q(apellido_m__icontains=texto) |
        Q(email__icontains=texto) |
        Q(email_institucional__icontains=texto) |
        Q(curp__icontains=texto) |
        Q(telefono__icontains=texto)
    )

    # potencia: intenta match por combinación nombre+apellidos
    if len(parts) >= 2:
        # algo como "juan perez" o "perez juan"
        p0 = parts[0]
        p1 = parts[1]
        q |= (Q(nombre__icontains=p0) & (Q(apellido_p__icontains=p1) | Q(apellido_m__icontains=p1)))
        q |= (Q(apellido_p__icontains=p0) & Q(nombre__icontains=p1))

    return (Alumno.objects
            .filter(q)
            .only('numero_estudiante','nombre','apellido_p','apellido_m','email','curp','telefono')
            [:limit])
