# alumnos/services/movimientos_loader.py
import re
import hashlib
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from datetime import datetime, date
from typing import Iterable, Mapping, Optional

from django.db import transaction
from alumnos.models import MovimientoBanco

# ---------------------------
# Normalización de fechas
# ---------------------------
DATE_ANY_RX = re.compile(r"\b(\d{1,4})[/-](\d{1,2})[/-](\d{2,4})\b")

def _clean_date_str(v: str) -> str:
    # quita comillas “smart” y dobles, y espacios de más
    return re.sub(r'[“”"]', "", (v or "")).strip()

def _parse_date(value) -> Optional[date]:
    """
    Acepta strings tipo:
      - YYYY-MM-DD
      - DD/MM/YYYY   (MX)
      - MM/DD/YYYY   (US)
      - con guiones o slashes; con o sin comillas “smart”.
    Devuelve datetime.date o None.
    """
    if not value:
        return None
    s = _clean_date_str(str(value))

    # Intento directo ISO
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        pass

    # Detecta 3 grupos numéricos
    m = DATE_ANY_RX.search(s)
    if not m:
        return None

    a, b, c = m.groups()
    a, b, c = int(a), int(b), int(c)

    # Normaliza año 2 dígitos
    if c < 100:
        c += 2000 if c < 70 else 1900

    # Si el primer grupo tiene 4 dígitos, es YYYY-M-D
    if len(str(a)) == 4:
        y, mth, d = a, b, c
    else:
        # Ambigüedad DD/MM vs MM/DD
        if b > 12:
            # DD/MM/YYYY
            d, mth, y = a, b, c
        else:
            # Si a > 12 => DD/MM/YYYY; si no => MM/DD/YYYY
            if a > 12:
                d, mth, y = a, b, c
            else:
                mth, d, y = a, b, c

    try:
        return date(y, mth, d)
    except ValueError:
        # Último intento con formatos comunes
        for fmt in ("%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%m-%d-%Y"):
            try:
                return datetime.strptime(s, fmt).date()
            except Exception:
                continue
    return None

# ---------------------------
# Normalización de números
# ---------------------------
def _to_decimal(x) -> Optional[Decimal]:
    if x in (None, "", "null"):
        return None
    s = str(x).strip()

    # El JSON ya viene como número o string. Si es string con formato latam/us:
    # - quitar símbolos
    s = s.replace("$", "").replace(" ", "")

    # Caso "1.234,56" -> "1234.56"
    if "." in s and "," in s and s.rfind(",") > s.rfind("."):
        s = s.replace(".", "").replace(",", ".")
    else:
        # Caso "1,234.56" -> "1234.56"
        s = s.replace(",", "")

    try:
        d = Decimal(s)
        # Normaliza a 2 decimales
        return d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        return None

# ---------------------------
# Normalización de signo
# ---------------------------
def _norm_sign(v) -> int:
    """
    Regla pedida:
      - si el JSON trae -1 => dinero que salió (egreso)
      - si NO es -1 => dinero que entró (ingreso) => 1
    Acepta int/str; cualquier cosa diferente a -1 se toma como 1.
    """
    if v is None:
        return 1
    try:
        n = int(str(v).strip())
        return -1 if n == -1 else 1
    except Exception:
        return 1

# ---------------------------
# Canonicalización para hash
# ---------------------------
def _canon_text(v) -> str:
    """Normaliza texto para el hash (espacios y mayúsculas)."""
    if v is None:
        return ""
    s = str(v).strip()
    return " ".join(s.split()).upper()

def _canon_date_for_hash(v) -> str:
    """Normaliza fecha para el hash (ISO YYYY-MM-DD)."""
    dt = _parse_date(v)
    return dt.isoformat() if isinstance(dt, date) else ""

def _canon_amount_for_hash(v) -> str:
    """Normaliza monto para el hash (dos decimales, solo magnitud positiva)."""
    d = _to_decimal(v)
    if isinstance(d, Decimal):
        if d < 0:
            d = -d
        return f"{d:.2f}"
    return ""

def _hash_mov(d: Mapping) -> str:
    """
    Genera un SHA1 estable con los campos que hacen único un movimiento.
    Usa fecha y monto CANÓNICOS y añade el SIGNO normalizado.
    """
    parts = [
        _canon_date_for_hash(d.get("fecha")),
        _canon_text(d.get("tipo")),
        _canon_amount_for_hash(d.get("monto")),
        str(_norm_sign(d.get("signo"))),              # <--- incluir signo
        _canon_text(d.get("sucursal")),
        _canon_text(d.get("referencia_numerica")),
        _canon_text(d.get("autorizacion")),
        _canon_text(d.get("emisor_nombre")),
        _canon_text(d.get("institucion_emisora")),
        _canon_text(d.get("concepto")),
        _canon_text(d.get("descripcion_raw")),
    ]
    base = "|".join(parts)
    return hashlib.sha1(base.encode("utf-8")).hexdigest()

# ---------------------------
# Upsert principal
# ---------------------------
@transaction.atomic
def upsert_movimientos(
    items: Iterable[Mapping],
    source_sheet_id: Optional[str] = None,
    source_sheet_name: Optional[str] = None,
    source_gid: Optional[str] = None,
) -> dict:
    """
    Inserta/actualiza movimientos desde una lista de diccionarios (el JSON).
    Retorna métricas: created/updated/skipped.
    """
    created = 0
    updated = 0
    skipped = 0

    for idx, d in enumerate(items, start=1):
        # Hash idempotente normalizado (fecha/monto/signo canónicos)
        uid = _hash_mov(d)

        # Normalizar monto a magnitud positiva
        monto = _to_decimal(d.get("monto"))
        if isinstance(monto, Decimal) and monto < 0:
            monto = -monto

        # Normalizar signo según la regla
        signo = _norm_sign(d.get("signo"))

        defaults = {
            "fecha": _parse_date(d.get("fecha")),    # date
            "tipo": d.get("tipo") or None,
            "monto": monto,                           # Decimal positivo
            "signo": signo,                           # -1 egreso, 1 ingreso
            "sucursal": (d.get("sucursal") or None),
            "referencia_numerica": (d.get("referencia_numerica") or None),
            "referencia_alfanumerica": d.get("referencia_alfanumerica") or None,
            "concepto": d.get("concepto") or None,
            "autorizacion": d.get("autorizacion") or None,
            "emisor_nombre": d.get("emisor_nombre") or None,
            "institucion_emisora": d.get("institucion_emisora") or None,
            "descripcion_raw": d.get("descripcion_raw") or None,
            "source_sheet_id": source_sheet_id,
            "source_sheet_name": source_sheet_name,
            "source_gid": source_gid,
            "source_row": idx,
        }

        obj, is_created = MovimientoBanco.objects.update_or_create(
            uid_hash=uid,
            defaults=defaults,
        )
        if is_created:
            created += 1
        else:
            updated += 1

    return {"created": created, "updated": updated, "skipped": skipped}
