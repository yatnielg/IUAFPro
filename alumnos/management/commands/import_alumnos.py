from django.core.management import BaseCommand, CommandError
from alumnos.models import Alumno, Programa   # <-- AÑADIDO
import pandas as pd
import re
from typing import Optional
from django.db.models import Q

# === Patrones para detectar columnas por nombre ===
CANDIDATOS = {
    "numero_estudiante": [
        r"^no\.?$",
        r"^n(ú|u)?m(ero)?\s*est(ud(i)?ante)?$",
        r"^no\.?\s*est(ud(i)?ante)?$",
        r"^(nro|n°)\s*est(ud(i)?ante)?$",
        r"^matr(í|i)cula$",
        r"^id\s*(alumno|estudiante)?$",
        r"^c(ó|o)digo(\s*alumno)?$",
        r"^num(ero)?$",
    ],
    "curp": [r"^curp$"],
    "nombre": [r"^nombre(s)?$"],
    "apellido_p": [r"^apellido\s*p(aterno)?$", r"^ap\.?\s*p$"],
    "apellido_m": [r"^apellido\s*m(aterno)?$", r"^ap\.?\s*m$"],
    "email": [r"^e-?mail$", r"^correo(\s*electr(ó|o)nico)?$"],
    "telefono": [r"^tel(é|e)fono$", r"^cel(ular)?$"],
    "programa": [r"^programa$", r"^carrera$", r"^curso$"],  # <-- aquí leeremos código o nombre
    "estatus": [r"^estatus$", r"^estado$"],
    "estatus_academico": [r"^estatus\s*acad(é|e)mico$"],
    "estatus_administrativo": [r"^estatus\s*administrativo$"],
}

# --- Utils ---
def _norm_cell(x):
    if pd.isna(x): return ""
    return str(x).strip()

def _norm_cols(cols):
    return [str(c).strip().lower() for c in cols]

def _match_col(cols, patrones):
    for p in patrones:
        reg = re.compile(p, re.I)
        for c in cols:
            if reg.match(c):
                return c
    return None

def _col_index_to_name(idx_or_letter: str, cols_len: int) -> Optional[int]:
    s = str(idx_or_letter).strip()
    if s.isdigit():
        i = int(s)
        return i if 0 <= i < cols_len else None
    s = s.upper()
    val = 0
    for ch in s:
        if not ('A' <= ch <= 'Z'):
            return None
        val = val * 26 + (ord(ch) - ord('A') + 1)
    return val - 1 if 0 <= val - 1 < cols_len else None

def _autodetect_header_row(raw_df: pd.DataFrame, max_scan: int = 50) -> Optional[int]:
    patrones = [re.compile(p, re.I) for p in (
        CANDIDATOS["numero_estudiante"] + CANDIDATOS["nombre"] + CANDIDATOS["curp"]
    )]
    max_rows = min(max_scan, len(raw_df))
    best_row, best_hits = None, -1
    for r in range(max_rows):
        row_vals = [_norm_cell(v) for v in raw_df.iloc[r].tolist()]
        hits = 0
        for val in row_vals:
            low = val.lower()
            for reg in patrones:
                if reg.match(low):
                    hits += 1
                    break
        if hits > best_hits and hits >= 1:
            best_hits, best_row = hits, r
    return best_row

def _clean_curp(val: str) -> Optional[str]:
    s = _norm_cell(val)
    if not s or s.lower() in ("nan", "none", "null"):
        return None
    return s.upper()

# --- Normalizadores para Programa ---
ALIAS_PROGRAMA = {
    "ACT DER": "ACTUALIZACION DERECHO",
    "DIP IA": "DIPLOMADO INT ARTIFICIAL",
    # agrega más si tu Excel trae abreviaturas particulares
}

def _key(s: str) -> str:
    """clave normalizada para índices (mayúsculas y espacios compactados)"""
    return " ".join(s.upper().split())

def _build_programa_index():
    """
    Crea dos diccionarios para resolver rápido:
      - por código (LD, MD, ...),
      - por nombre normalizado (LICENCIATURA EN DERECHO, ...).
    """
    by_codigo = {}
    by_nombre = {}
    for p in Programa.objects.all():
        if p.codigo:
            by_codigo[_key(p.codigo)] = p
        if p.nombre:
            by_nombre[_key(p.nombre)] = p
    return by_codigo, by_nombre

def _resolve_programa(excel_val: str, by_codigo, by_nombre) -> Optional[Programa]:
    s = _norm_cell(excel_val)
    if not s:
        return None
    s = ALIAS_PROGRAMA.get(s, s)
    k = _key(s)
    # 1) intenta código exacto
    p = by_codigo.get(k)
    if p:
        return p
    # 2) intenta nombre exacto
    p = by_nombre.get(k)
    if p:
        return p
    return None

# === Command ===
class Command(BaseCommand):
    help = "Importa/actualiza alumnos desde Excel respetando el número de estudiante como ID."

    def add_arguments(self, parser):
        parser.add_argument("file", help="Ruta al .xlsx/.xlsm")
        parser.add_argument("--sheet", default="BASE ALUMNOS", help="Nombre de hoja")
        parser.add_argument("--id-col", default=None, help="Encabezado EXACTO del Número de Estudiante")
        parser.add_argument("--id-col-index", default=None, help="Índice/col del ID (A o 0)")
        parser.add_argument("--header-row", type=int, default=None, help="Fila 1-based con encabezados")

    def handle(self, file, sheet, id_col, id_col_index, header_row, **kwargs):
        # 1) Lee en crudo
        try:
            raw = pd.read_excel(file, sheet_name=sheet, header=None, engine="openpyxl")
        except Exception as e:
            raise CommandError(f"No pude leer el Excel: {e}")

        # 2) Encabezados
        header_idx = max(0, header_row - 1) if header_row else (_autodetect_header_row(raw) or 0)

        # 3) Relee con encabezados
        try:
            df = pd.read_excel(file, sheet_name=sheet, header=header_idx, engine="openpyxl")
        except Exception as e:
            raise CommandError(f"No pude re-leer el Excel con encabezados (fila {header_idx+1}): {e}")

        orig_cols = list(df.columns)
        df.columns = _norm_cols(df.columns)
        cols = list(df.columns)

        # 4) ID alumno
        id_col_norm = None
        if id_col:
            cand = id_col.strip().lower()
            if cand not in cols:
                raise CommandError(f"La columna '{id_col}' no existe. Encabezados: {orig_cols}")
            id_col_norm = cand
        if id_col_norm is None and id_col_index is not None:
            idx = _col_index_to_name(id_col_index, len(cols))
            if idx is None:
                raise CommandError(f"--id-col-index inválido: {id_col_index}. Usa 'A'.. o '0'..'{len(cols)-1}'")
            id_col_norm = cols[idx]
        if id_col_norm is None:
            id_col_norm = _match_col(cols, CANDIDATOS["numero_estudiante"])
        if not id_col_norm:
            raise CommandError("No encontré la columna del Número de Estudiante. Encabezados: " + ", ".join(map(str, orig_cols)))

        # 5) Mapear columnas
        mapeo = {"numero_estudiante": id_col_norm}
        for campo, patrones in CANDIDATOS.items():
            if campo == "numero_estudiante":
                continue
            col = _match_col(cols, patrones)
            if col:
                mapeo[campo] = col

        # 6) Índices de Programas para resolver rápido
        by_codigo, by_nombre = _build_programa_index()

        creados = actualizados = 0

        # 7) Loop
        for _, r in df.iterrows():
            num = _norm_cell(r.get(mapeo["numero_estudiante"]))
            if not num:
                continue

            curp_val = _clean_curp(r.get(mapeo.get("curp"))) if "curp" in mapeo else None
            if curp_val and Alumno.objects.exclude(numero_estudiante=num).filter(curp=curp_val).exists():
                self.stdout.write(self.style.WARNING(
                    f"Conflicto de CURP '{curp_val}' para estudiante {num}. Ya existe en otro alumno. Se ignora en esta fila."
                ))
                curp_val = None

            # === RESOLVER PROGRAMA (FK) ===
            prog_obj = None
            if "programa" in mapeo:
                prog_val = _norm_cell(r.get(mapeo.get("programa")))
                prog_obj = _resolve_programa(prog_val, by_codigo, by_nombre)
                if prog_val and not prog_obj:
                    self.stdout.write(self.style.WARNING(
                        f"[{num}] Programa no encontrado para '{prog_val}'. Se dejará sin programa."
                    ))

            datos = {
                "curp": curp_val,
                "estatus_academico": _norm_cell(r.get(mapeo.get("estatus_academico"))),
                "estatus_administrativo": _norm_cell(r.get(mapeo.get("estatus_administrativo"))),
                "nombre": _norm_cell(r.get(mapeo.get("nombre"))),
                "apellido_p": _norm_cell(r.get(mapeo.get("apellido_p"))),
                "apellido_m": _norm_cell(r.get(mapeo.get("apellido_m"))),
                "email": _norm_cell(r.get(mapeo.get("email"))),
                "telefono": _norm_cell(r.get(mapeo.get("telefono"))),
                "programa": prog_obj,   # <-- INSTANCIA o None
                "estatus": _norm_cell(r.get(mapeo.get("estatus"))),
            }

            obj, created = Alumno.objects.update_or_create(
                numero_estudiante=num,
                defaults=datos
            )
            creados += int(created)
            actualizados += int(not created)

        self.stdout.write(self.style.SUCCESS(
            f"Listo: creados {creados}, actualizados {actualizados}. (Hoja: {sheet}, encabezados en fila {header_idx+1})"
        ))
