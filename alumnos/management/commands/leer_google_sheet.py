import re
import sys
import json
import tempfile
from pathlib import Path
from typing import Optional, Tuple
import pandas as pd
from datetime import datetime
from django.core.management.base import BaseCommand

import io
import requests
import urllib.error

from django.core.management.base import BaseCommand, CommandError

# =======================
# Defaults ajustables
# =======================
SHEET_ID_DEFAULT = "1G0P64LVOfxG4siNXmTm0gCORoaPby2W2_wu0Z869Dvk"
GID_DEFAULT = "1206699819"
SHEET_NAME_DEFAULT = "2022"

# =======================
# URL helpers
# =======================
def csv_url_by_gid(sheet_id: str, gid: str) -> str:
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"

def csv_url_by_name(sheet_id: str, sheet_name: str) -> str:
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet={sheet_name}"

def parse_sheet_url(url: str) -> Tuple[Optional[str], Optional[str]]:
    m = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", url)
    sheet_id = m.group(1) if m else None
    gid = None
    mg = re.search(r"[?&]gid=([0-9]+)", url)
    if mg:
        gid = mg.group(1)
    return sheet_id, gid

# =======================
# Regex y utilidades
# =======================
AMOUNT_RX = re.compile(r"(-?\s?\$?\s?\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?)")
DATE_INLINE_RX = re.compile(r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b")
MONEY_CELL_RX = re.compile(r"^\s*-?\(?\$?\s*\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})\)?\s*$")

def clean_numeric_token(s: Optional[str]) -> Optional[str]:
    if s is None: return None
    ss = str(s).strip()
    if ss in ("", "-", "–", "—"):  # guiones y vacío = None
        return None
    return ss

def to_float(monto_str: Optional[str]):
    s = clean_numeric_token(monto_str)
    if s is None:
        return None
    # paréntesis -> negativo
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    # quitar símbolos
    s = s.replace("$", "").replace(" ", "").replace(",", "")
    # caso latino 1.234,56
    if "." in s and "," in s and s.rfind(",") > s.rfind("."):
        s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except Exception:
        return None

def parse_fecha(fecha_str: Optional[str]):
    if not fecha_str:
        return None
    s = str(fecha_str).strip()
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%y", "%d-%m-%y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except Exception:
            pass
    m = DATE_INLINE_RX.search(s)
    if m:
        cand = m.group(1).replace("-", "/")
        for fmt in ("%d/%m/%Y", "%d/%m/%y"):
            try:
                return datetime.strptime(cand, fmt).date().isoformat()
            except Exception:
                continue
        return cand
    return None  # si no hay fecha válida, mejor None (muchas filas de encabezado)

FIELD_RXS = {
    "sucursal": re.compile(r"Sucursal:\s*([0-9A-Za-z/.\-]+)"),
    "referencia_numerica": re.compile(r"Referencia\s+Num[eé]rica:\s*([0-9A-Za-z/.\-]+)"),
    "referencia_alfanumerica": re.compile(r"Referencia\s+alfanum[eé]rica:\s*([^N]+?)(?:No\.|\bInstituci[oó]n|\bNombre|\bConcepto|$)"),
    "concepto": re.compile(r"Concepto\s+del\s+Pago:\s*([^N]+?)(?:No\.|\bInstituci[oó]n|\bNombre|$)"),
    "autorizacion": re.compile(r"No\.\s*de\s*Autorizaci[oó]n:\s*([0-9A-Za-z/.\-]+)"),
    "emisor_nombre": re.compile(r"Nombre\s+del\s+Emisor:\s*(.+?)\s+(?:Instituci[oó]n\s+Emisora|$)"),
    "institucion_emisora": re.compile(r"Instituci[oó]n\s+Emisora:\s*([A-ZÁÉÍÓÚÑa-z0-9\s./&]+)"),
}

def first_in_quotes(text: str):
    m = re.search(r"“([^”]+)”|\"([^\"]+)\"", text)
    if m:
        return (m.group(1) or m.group(2)).strip()
    return None

def guess_tipo(text: str):
    q = first_in_quotes(text)
    base = (q or text or "").strip()
    for t in [
        "Abono Interbancario", "Abono por cobranza", "Abono a", "Depósito en Efectivo",
        "Pago Interbancario", "Pago a terceros", "Pago de servicio",
        "Cargo diverso", "Abono", "Pago"
    ]:
        if t.lower() in base.lower():
            return t
    return " ".join(base.split()[:3]) or None

def parse_desc_fields(desc: str):
    out = {}
    for k, rx in FIELD_RXS.items():
        m = rx.search(desc)
        if m:
            out[k] = m.group(1).strip().rstrip('"').rstrip()
    out["tipo"] = guess_tipo(desc)
    return out

# =======================
# Columns helpers
# =======================
# palabras para detectar columnas de SALDO/TOTAL/FACTURA (a excluir del monto)
SALDO_WORDS = [
    "saldo", "balance", "total", "factura", "marcar", "realizadas", "acumulado",
    "restante", "resto", "por pagar", "por cobrar", "utilidad", "quedó", "quedo"
]
def is_saldo_header(name: Optional[str]) -> bool:
    if not name:
        return False
    n = str(name).lower()
    return any(w in n for w in SALDO_WORDS)

def score_date_col(series: pd.Series) -> int:
    cnt = 0
    for v in series.astype(str).head(200):
        if DATE_INLINE_RX.search(v.strip()):
            cnt += 1
    return cnt

def score_money_col(series: pd.Series) -> int:
    cnt = 0
    for v in series.astype(str).head(200):
        if MONEY_CELL_RX.match(v.strip()):
            cnt += 1
    return cnt

def score_text_col(series: pd.Series) -> float:
    s = series.astype(str).fillna("")
    return s.map(len).head(200).mean()

def norm(s: str) -> str:
    return s.strip().lower()

def detect_columns(df: pd.DataFrame):
    # 1) match exactos primero
    headers = {norm(c): c for c in df.columns}

    abono_exact = None
    for key in ["ingresos (en banco)", "ingresos en banco", "ingresos"]:
        if key in headers: abono_exact = headers[key]; break

    cargo_exact = None
    for key in ["egresos"]:
        if key in headers: cargo_exact = headers[key]; break

    fecha_exact = None
    for key in ["fecha"]:
        if key in headers: fecha_exact = headers[key]; break

    desc_exact = None
    for key in ["concepto", "concepto ", "descripcion", "descripción", "detalle", "movimiento", "referencia"]:
        if key in headers: desc_exact = headers[key]; break

    col_abono = abono_exact
    col_cargo = cargo_exact
    col_fecha = fecha_exact
    col_desc  = desc_exact

    # 2) si falta fecha -> heurística
    if not col_fecha:
        scores = {c: score_date_col(df[c]) for c in df.columns}
        if scores:
            best = max(scores, key=scores.get)
            if scores[best] > 0:
                col_fecha = best

    # 3) construir candidatos monetarios excluyendo totales/saldos/fecha/desc
    money_scores = {c: score_money_col(df[c]) for c in df.columns}
    excluded = {c for c in df.columns if is_saldo_header(c)}
    if col_desc:  excluded.add(col_desc)
    if col_fecha: excluded.add(col_fecha)
    money_candidates = [c for c in sorted(money_scores, key=money_scores.get, reverse=True) if c not in excluded]

    # 4) completar SOLO lo que falte (no sobreescribir exactos)
    def has_neg(col):
        for v in df[col].astype(str).head(200):
            vv = v.strip()
            if "-" in vv or "(" in vv:
                return True
        return False

    if not col_abono and not col_cargo:
        if len(money_candidates) >= 2:
            top2 = money_candidates[:2]
            if has_neg(top2[0]) and not has_neg(top2[1]):
                col_cargo, col_abono = top2[0], top2[1]
            elif has_neg(top2[1]) and not has_neg(top2[0]):
                col_cargo, col_abono = top2[1], top2[0]
            else:
                col_cargo, col_abono = top2[0], top2[1]
        elif len(money_candidates) == 1:
            # única columna: por defecto abono
            col_abono = money_candidates[0]
    elif col_abono and not col_cargo:
        for c in money_candidates:
            if c != col_abono:
                col_cargo = c
                break
    elif col_cargo and not col_abono:
        for c in money_candidates:
            if c != col_cargo:
                col_abono = c
                break

    # 5) si no hay descripción, elige la más “larga”
    if not col_desc:
        text_scores = {c: score_text_col(df[c]) for c in df.columns}
        if text_scores:
            col_desc = max(text_scores, key=text_scores.get)

    # 6) blindaje: nunca usar columnas saldo/total/factura como montos
    if col_abono and is_saldo_header(col_abono): col_abono = None
    if col_cargo and is_saldo_header(col_cargo): col_cargo = None

    return col_desc, col_cargo, col_abono, col_fecha, money_candidates

# =======================
# Parse por fila
# =======================
def parse_row_with_columns(row, col_desc, col_cargo, col_abono, col_fecha, has_money_cols: bool):
    desc = str(row[col_desc]) if col_desc else ""
    fecha = parse_fecha(row[col_fecha]) if col_fecha else None

    # Nunca usar columnas de saldo/total/factura como monto
    if col_abono and is_saldo_header(col_abono):
        col_abono = None
    if col_cargo and is_saldo_header(col_cargo):
        col_cargo = None

    cargo = to_float(row[col_cargo]) if col_cargo else None
    abono = to_float(row[col_abono]) if col_abono else None

    # Si sólo hay una columna de importe (no etiquetada como cargo/abono)
    if cargo is None and abono is not None and (("cargo" not in (col_abono or "").lower()) and ("abono" not in (col_abono or "").lower()) and ("egreso" not in (col_abono or "").lower()) and ("ingreso" not in (col_abono or "").lower())):
        lower = desc.lower()
        if any(w in lower for w in ["cargo", "pago", "retiro", "servicio", "comisión", "comision", "debit", "compra"]):
            cargo, abono = abono, None  # tratar como egreso
        # si no, queda como ingreso por defecto

    fields = parse_desc_fields(desc)

    monto = None
    signo = None
    if cargo is not None and cargo != 0:
        monto = cargo
        signo = 1          # <- cargo ahora cuenta como INGRESO
    if abono is not None and abono != 0 and monto is None:
        monto = abono
        signo = -1         # <- abono ahora cuenta como EGRESO

    # IMPORTANTÍSIMO:
    # Si el DF tiene columnas monetarias (ingresos/egresos), NO intentamos rescate desde la descripción.
    if monto is None and not has_money_cols:
        m = AMOUNT_RX.findall(desc)
        if m:
            monto = to_float(m[-1])

    # Si la fila no tiene fecha válida y tampoco monto, probablemente es encabezado/nota -> ignorar
    if not fecha and monto is None and not desc:
        return None

    return {
        "fecha": fecha,
        "tipo": fields.get("tipo"),
        "monto": monto,
        "signo": signo,  # 1=abono, -1=cargo, None=indeterminado
        "sucursal": fields.get("sucursal"),
        "referencia_numerica": fields.get("referencia_numerica"),
        "referencia_alfanumerica": fields.get("referencia_alfanumerica"),
        "concepto": fields.get("concepto"),
        "autorizacion": fields.get("autorizacion"),
        "emisor_nombre": fields.get("emisor_nombre"),
        "institucion_emisora": fields.get("institucion_emisora"),
        "descripcion_raw": desc,
    }

def parse_single_text_cell(text: str):
    parts = re.split(r'(?=\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b)', text)
    out = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        fecha = parse_fecha(p)
        mnums = AMOUNT_RX.findall(p)
        monto = to_float(mnums[-1]) if mnums else None
        fields = parse_desc_fields(p)
        out.append({
            "fecha": fecha,
            "tipo": fields.get("tipo"),
            "monto": monto,
            "signo": None,
            "sucursal": fields.get("sucursal"),
            "referencia_numerica": fields.get("referencia_numerica"),
            "referencia_alfanumerica": fields.get("referencia_alfanumerica"),
            "concepto": fields.get("concepto"),
            "autorizacion": fields.get("autorizacion"),
            "emisor_nombre": fields.get("emisor_nombre"),
            "institucion_emisora": fields.get("institucion_emisora"),
            "descripcion_raw": p,
        })
    return out

# =======================
# Management command
# =======================
class Command(BaseCommand):
    help = "Lee un Google Sheet y devuelve los movimientos como lista de diccionarios."

    def add_arguments(self, parser):
        parser.add_argument("--url", help="URL compartido del Google Sheet (opcional).")
        parser.add_argument("--por", choices=["gid", "nombre", "auto"], default="auto",
                            help="Usar 'gid', 'nombre' o 'auto'.")
        parser.add_argument("--sheet-id", help="Forzar sheet_id si no usas --url.")
        parser.add_argument("--gid", help="Forzar gid explícito si usas 'gid'.")
        parser.add_argument("--sheet-name", help="Nombre de la hoja si usas 'nombre'.")
        parser.add_argument("--mostrar-head", action="store_true",
                            help="Muestra df.head() al inicio.")
        parser.add_argument("--limite", type=int, default=0,
                            help="Si >0, limita número de filas antes de parsear.")
        parser.add_argument("--out-json", help="Ruta para guardar el JSON de movimientos.")
        parser.add_argument("--debug", action="store_true",
                            help="Imprime columnas y primeras filas para diagnóstico.")
        parser.add_argument("--col-fecha")
        parser.add_argument("--col-descripcion")
        parser.add_argument("--col-cargo")
        parser.add_argument("--col-abono")

    def handle(self, *args, **opts):
        url_arg = opts.get("url")
        por = opts["por"]
        limite = opts["limite"]
        debug = opts["debug"]

        # --- Resolver sheet_id / gid / nombre ---
        sheet_id = None
        detected_gid = None
        if url_arg:
            sheet_id, detected_gid = parse_sheet_url(url_arg)
            if not sheet_id:
                self.stderr.write(self.style.ERROR("No pude extraer el sheet_id del URL."))
                sys.exit(1)
        sheet_id = sheet_id or opts.get("sheet_id") or SHEET_ID_DEFAULT

        gid = opts.get("gid")
        sheet_name = opts.get("sheet_name")

        selected_mode = por
        if por == "auto":
            if sheet_name or SHEET_NAME_DEFAULT:
                selected_mode = "nombre"
                sheet_name = sheet_name or SHEET_NAME_DEFAULT
            elif detected_gid:
                selected_mode = "gid"
                gid = gid or detected_gid
            else:
                selected_mode = "gid"
                gid = gid or GID_DEFAULT

        if selected_mode == "gid":
            gid = gid or detected_gid or GID_DEFAULT
            csv_url = csv_url_by_gid(sheet_id, gid)
            self.stdout.write(self.style.NOTICE(f"Modo: GID ({gid})"))
        else:
            sheet_name = sheet_name or SHEET_NAME_DEFAULT
            if not sheet_name:
                self.stderr.write(self.style.ERROR("Falta --sheet-name para modo 'nombre'."))
                sys.exit(1)
            csv_url = csv_url_by_name(sheet_id, sheet_name)
            self.stdout.write(self.style.NOTICE(f"Modo: NOMBRE ({sheet_name})"))

        self.stdout.write(self.style.NOTICE(f"Leyendo CSV desde:\n{csv_url}\n"))

        # --- Leer CSV ---
        try:
            df = pd.read_csv(csv_url, dtype=str, keep_default_na=False)
        except Exception as e:
            self.stderr.write(self.style.ERROR(
                "No se pudo leer el Google Sheet (asegura permiso público o publicado).\n"
                f"Error: {e}"
            ))
            sys.exit(1)

        if debug or opts["mostrar_head"]:
            self.stdout.write(self.style.HTTP_INFO(f"\nColumnas detectadas: {list(df.columns)}"))
            self.stdout.write(self.style.HTTP_INFO("Primeras 3 filas crudas:"))
            # print(df.head(3).to_string(index=False))

        if limite and limite > 0:
            df = df.iloc[:limite].copy()

        movimientos = []

        # --- Caso: una sola columna (texto largo) ---
        if df.shape[1] == 1:
            col = df.columns[0]
            for txt in df[col].tolist():
                if not str(txt).strip():
                    continue
                movimientos.extend(parse_single_text_cell(str(txt)))

        else:
            # Override manual
            col_desc = opts.get("col_descripcion")
            col_cargo = opts.get("col_cargo")
            col_abono = opts.get("col_abono")
            col_fecha = opts.get("col_fecha")

            # Detección automática (con preferencias duras)
            if not (col_desc and (col_cargo or col_abono) and col_fecha):
                auto_desc, auto_cargo, auto_abono, auto_fecha, money_candidates = detect_columns(df)
                col_desc  = col_desc  or auto_desc
                col_cargo = col_cargo or auto_cargo
                col_abono = col_abono or auto_abono
                col_fecha = col_fecha or auto_fecha
            else:
                # si el usuario fuerza columnas, consideramos que hay columnas monetarias
                money_candidates = [c for c in [col_abono, col_cargo] if c]

            if debug:
                self.stdout.write(self.style.HTTP_INFO(
                    f"Usando columnas -> desc:{col_desc} | cargo:{col_cargo} | abono:{col_abono} | fecha:{col_fecha}"
                ))

            # Si la “descripción” viene muy vacía, concatenar SOLO columnas NO-monetarias ni de saldo
            try:
                empty_ratio = df[col_desc].astype(str).str.strip().eq("").mean() if col_desc else 1.0
            except Exception:
                empty_ratio = 1.0
            if empty_ratio > 0.5:
                non_money_cols = [
                    c for c in df.columns
                    if score_money_col(df[c]) == 0 and not is_saldo_header(c)
                ]
                df["__desc_join__"] = df[non_money_cols].astype(str).agg(" | ".join, axis=1)
                col_desc = "__desc_join__"
                if debug:
                    self.stdout.write(self.style.HTTP_INFO(
                        "Descripción débil: usando concatenación de columnas NO monetarias (__desc_join__)"
                    ))

            has_money_cols = bool([c for c in money_candidates if c])

            # Iterar filas
            for _, row in df.iterrows():
                rec = parse_row_with_columns(row, col_desc, col_cargo, col_abono, col_fecha, has_money_cols)
                if rec is not None:
                    movimientos.append(rec)

        self.stdout.write(self.style.SUCCESS("\nMovimientos (lista de diccionarios):"))

        out_json_arg = opts.get("out_json")
        if out_json_arg is None or str(out_json_arg).strip() == "":
            base = f"movimientos_{(sheet_name or gid or 'sheet')}.json"
            out_json_arg = str(Path(tempfile.gettempdir()) / base)

        out_path = Path(out_json_arg)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with out_path.open("w", encoding="utf-8") as f:
                json.dump(movimientos, f, ensure_ascii=False, indent=2)
            self.stdout.write(self.style.SUCCESS(f"\nJSON guardado en: {out_path}"))
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"No se pudo guardar el JSON en '{out_path}'. Error: {e}"))

        self.stdout.write(self.style.SUCCESS(f"\nTotal movimientos: {len(movimientos)}"))


# Ejemplo:
# python manage.py leer_google_sheet --por nombre --out-json ".\salidas\movimientos_2025-11.json" --debug
