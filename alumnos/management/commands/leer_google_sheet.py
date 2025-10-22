import re
import sys
import json
import tempfile
from pathlib import Path
from typing import Optional
import pandas as pd
from datetime import datetime
from django.core.management.base import BaseCommand

# =======================
# Defaults ajustables
# =======================
# ID del Google Sheet que ya "sabemos"
SHEET_ID_DEFAULT = "1G0P64LVOfxG4siNXmTm0gCORoaPby2W2_wu0Z869Dvk"
# Si algún día prefieres usar GID, pon aquí el de la pestaña 2022:
GID_DEFAULT = "1206699819"
# Leer por nombre de hoja (recomendado)
SHEET_NAME_DEFAULT = "2022"

# =======================
# URL helpers
# =======================
def csv_url_by_gid(sheet_id: str, gid: str) -> str:
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"

def csv_url_by_name(sheet_id: str, sheet_name: str) -> str:
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet={sheet_name}"

def parse_sheet_url(url: str):
    """
    Extrae (sheet_id, gid?) del URL de Google Sheets.
    """
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
MONEY_CELL_RX = re.compile(r"^\s*-?\$?\s*\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})\s*$")

def to_float(monto_str: Optional[str]):
    if monto_str is None:
        return None
    s = str(monto_str).strip()
    if s == "":
        return None
    s = s.replace("$", "").replace(" ", "").replace(",", "")
    # caso latino: "1.234,56" -> 1234.56
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
    # intento: detectar dentro del texto
    m = DATE_INLINE_RX.search(s)
    if m:
        cand = m.group(1).replace("-", "/")
        for fmt in ("%d/%m/%Y", "%d/%m/%y"):
            try:
                return datetime.strptime(cand, fmt).date().isoformat()
            except Exception:
                continue
        return cand
    return s  # fallback: devuelve crudo

FIELD_RXS = {
    "sucursal": re.compile(r"Sucursal:\s*([0-9A-Za-z/.-]+)"),
    "referencia_numerica": re.compile(r"Referencia\s+Num[eé]rica:\s*([0-9A-Za-z/.-]+)"),
    "referencia_alfanumerica": re.compile(r"Referencia\s+alfanum[eé]rica:\s*([^N]+?)(?:No\.|\bInstituci[oó]n|\bNombre|\bConcepto|$)"),
    "concepto": re.compile(r"Concepto\s+del\s+Pago:\s*([^N]+?)(?:No\.|\bInstituci[oó]n|\bNombre|$)"),
    "autorizacion": re.compile(r"No\.\s*de\s*Autorizaci[oó]n:\s*([0-9A-Za-z/.-]+)"),
    "emisor_nombre": re.compile(r"Nombre\s+del\s+Emisor:\s*(.+?)\s+Instituci[oó]n\s+Emisora:"),
    "institucion_emisora": re.compile(r"Instituci[oó]n\s+Emisora:\s*([A-ZÁÉÍÓÚÑa-z0-9\s\.\/&]+)"),
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
# Detección de columnas
# =======================
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
    return s.map(lambda x: len(x)).head(200).mean()

def detect_columns(df: pd.DataFrame):
    name_map = {c.lower(): c for c in df.columns}

    def find_by_keywords(keywords):
        for k, orig in name_map.items():
            if any(w in k for w in keywords):
                return orig
        return None

    col_fecha = find_by_keywords(["fecha", "operaci", "aplicaci"])
    col_cargo = find_by_keywords(["cargo", "retiro", "cargos", "egreso", "debit", "débito"])
    col_abono = find_by_keywords(["abono", "deposit", "ingreso", "credito", "crédito"])
    col_desc  = find_by_keywords(["descrip", "concepto", "detalle", "movimiento", "referen"])

    # Heurística por contenido si faltan
    if not col_fecha:
        scores = {c: score_date_col(df[c]) for c in df.columns}
        if scores:
            best = max(scores, key=scores.get)
            if scores[best] > 0:
                col_fecha = best

    money_scores = {c: score_money_col(df[c]) for c in df.columns}
    money_candidates = sorted(money_scores, key=money_scores.get, reverse=True)

    if not col_abono or not col_cargo:
        if money_candidates and money_scores[money_candidates[0]] >= 3:
            # si no hay abono/cargo explícitos, tomamos la mejor como "importe"
            if not col_abono and not col_cargo:
                col_abono = money_candidates[0]
        if len(money_candidates) >= 2 and (not col_abono or not col_cargo):
            top2 = money_candidates[:2]
            def has_neg(col):
                for v in df[col].astype(str).head(200):
                    vv = v.strip()
                    if "-" in vv or "(" in vv:
                        return True
                return False
            if has_neg(top2[0]) and not has_neg(top2[1]):
                col_cargo, col_abono = top2[0], top2[1]
            elif has_neg(top2[1]) and not has_neg[top2[0]]:  # noqa: E741 (legibilidad)
                col_cargo, col_abono = top2[1], top2[0]
            else:
                col_cargo, col_abono = top2[0], top2[1]

    if not col_desc:
        text_scores = {c: score_text_col(df[c]) for c in df.columns}
        if text_scores:
            col_desc = max(text_scores, key=text_scores.get)

    return col_desc, col_cargo, col_abono, col_fecha

# =======================
# Parse por fila
# =======================
def parse_row_with_columns(row, col_desc, col_cargo, col_abono, col_fecha):
    desc = str(row[col_desc]) if col_desc else ""
    fecha = parse_fecha(row[col_fecha]) if col_fecha else None

    cargo = to_float(row[col_cargo]) if col_cargo else None
    abono = to_float(row[col_abono]) if col_abono else None

    # Si sólo hay una columna de importe (p.ej. col_abono es realmente "importe")
    if cargo is None and abono is not None and (("cargo" not in col_abono.lower()) and ("abono" not in col_abono.lower())):
        lower = desc.lower()
        if any(w in lower for w in ["cargo", "pago", "retiro", "servicio", "comisión", "comision", "debit", "compra"]):
            cargo, abono = abono, None  # tratar como egreso
        else:
            # por defecto, ingreso
            pass

    fields = parse_desc_fields(desc)

    monto = None
    signo = None
    if cargo is not None and cargo != 0:
        monto = cargo
        signo = -1
    if abono is not None and abono != 0:
        monto = abono
        signo = 1

    # Sin columnas de monto: intentar desde descripción
    if monto is None:
        m = AMOUNT_RX.findall(desc)
        if m:
            monto = to_float(m[-1])

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
    """
    Caso donde todo viene concatenado en una sola celda grande.
    Se intenta cortar por fechas dd/mm/yyyy o dd-mm-yyyy y luego parsear.
    """
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

        # Mapeo manual de columnas
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
            #print(df.head(3).to_string(index=False))

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
            # Mapeo manual (si lo pasan por CLI)
            col_desc = opts.get("col_descripcion")
            col_cargo = opts.get("col_cargo")
            col_abono = opts.get("col_abono")
            col_fecha = opts.get("col_fecha")

            # Si no está completo, detectar automáticamente
            if not (col_desc and (col_cargo or col_abono) and col_fecha):
                auto_desc, auto_cargo, auto_abono, auto_fecha = detect_columns(df)
                col_desc = col_desc or auto_desc
                col_cargo = col_cargo or auto_cargo
                col_abono = col_abono or auto_abono
                col_fecha = col_fecha or auto_fecha

            if debug:
                self.stdout.write(self.style.HTTP_INFO(
                    f"Usando columnas -> desc:{col_desc} | cargo:{col_cargo} | abono:{col_abono} | fecha:{col_fecha}"
                ))

            # Si la “descripción” viene muy vacía, concatenar columnas de texto
            try:
                empty_ratio = df[col_desc].astype(str).str.strip().eq("").mean() if col_desc else 1.0
            except Exception:
                empty_ratio = 1.0
            if empty_ratio > 0.5:
                text_cols = [c for c in df.columns if df[c].dtype == object]
                df["__desc_join__"] = df[text_cols].astype(str).agg(" | ".join, axis=1)
                col_desc = "__desc_join__"
                if debug:
                    self.stdout.write(self.style.HTTP_INFO("Descripción débil: usando concatenación de columnas de texto (__desc_join__)"))

            # Iterar filas
            for _, row in df.iterrows():
                movimientos.append(
                    parse_row_with_columns(row, col_desc, col_cargo, col_abono, col_fecha)
                )

        # --- Salida en consola ---
        self.stdout.write(self.style.SUCCESS("\nMovimientos (lista de diccionarios):"))
        #print(json.dumps(movimientos, ensure_ascii=False, indent=2))

        # --- Guardar JSON si se pidió ---
        out_json_arg = opts.get("out_json")
        if out_json_arg is None or str(out_json_arg).strip() == "":
            # ruta por defecto en tempdir con nombre según hoja/gid
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



#python manage.py leer_google_sheet --por nombre --out-json ".\salidas\movimientos_2022.json" --debug