# alumnos/management/commands/importar_diario.py
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from decimal import Decimal, InvalidOperation
from datetime import datetime, date
import pandas as pd
import re
import math

from alumnos.models import Alumno, PagoDiario


# ==============================================================
# Helpers seguros de normalización
# ==============================================================

def s(val):
    """
    Devuelve str.strip() o None si viene vacío, NaN o None.
    """
    if val is None:
        return None
    if isinstance(val, float) and math.isnan(val):
        return None
    txt = str(val).strip()
    if txt in ("", "NaT", "nan", "None"):
        return None
    return txt


def i(val):
    """
    Convierte a entero (acepta 123, '123', 123.0, '123.0').
    """
    txt = s(val)
    if not txt:
        return None
    try:
        return int(float(txt))
    except Exception:
        return None


def d(val):
    """
    Convierte a Decimal (quita $, comas, espacios).
    """
    txt = s(val)
    if not txt:
        return None
    for ch in ("$", ",", " "):
        txt = txt.replace(ch, "")
    try:
        return Decimal(txt)
    except (InvalidOperation, ValueError):
        return None


def f(val):
    """
    Convierte a date (admite datetime, pandas.Timestamp, serial excel, o texto).
    """
    if isinstance(val, (datetime, date)):
        return val.date() if isinstance(val, datetime) else val

    txt = s(val)
    if not txt:
        return None

    # Intentos con formatos comunes
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(txt, fmt).date()
        except ValueError:
            pass

    # Fallback con pandas (maneja muchos formatos). Si NaT, devuelve None.
    try:
        ts = pd.to_datetime(txt, dayfirst=True, errors="coerce")
        if pd.isna(ts):
            return None
        if isinstance(ts, datetime):
            return ts.date()
        # pandas puede devolver Timestamp
        return ts.to_pydatetime().date()
    except Exception:
        return None


def folio_norm(val):
    """
    Normaliza folio a string. Si viene '3003.0' => '3003'.
    Mantiene alfanuméricos tal cual (5V, 1OP, etc.).
    """
    txt = s(val)
    if not txt:
        return None
    try:
        if re.fullmatch(r"\d+(\.0+)?", txt):
            return str(int(float(txt)))
    except Exception:
        pass
    return txt


# ==============================================================
# Mapeo de columnas
# ==============================================================

COLMAP = {
    "folio": "folio",
    "sede": "sede",
    "nombre": "nombre",
    "monto": "monto",
    "grado": "grado",
    "forma_de_pago": "forma_pago",
    "forma_de_pago_": "forma_pago",
    "fecha": "fecha",
    "concepto": "concepto",
    "pago": "pago_detalle",
    "programa": "programa",
    "no_de_auto": "no_auto",
    "no._de_auto": "no_auto",
    "curp": "curp",
    "no_alumno": "numero_alumno",
    "no.alumno": "numero_alumno",
    "emision": "emision",
    "emisión": "emision",
}


def norm(sv: str) -> str:
    """
    Normaliza nombres de columna (minúsculas, _ en vez de espacios y signos, sin tildes).
    """
    if not isinstance(sv, str):
        return sv
    sv = sv.strip().lower()
    sv = sv.replace(" ", "_").replace("-", "_").replace(".", "_").replace("/", "_").replace("°", "")
    sv = sv.replace("__", "_")
    for k, v in {"ó": "o", "í": "i", "á": "a", "é": "e", "ú": "u", "ñ": "n"}.items():
        sv = sv.replace(k, v)
    return sv


# ==============================================================
# Comando principal (CREAR SIEMPRE, NUNCA ACTUALIZAR)
# ==============================================================

class Command(BaseCommand):
    help = "Importa pagos desde la hoja DIARIO del Excel IUAF (solo CREA, no actualiza)"

    def add_arguments(self, parser):
        parser.add_argument("archivo", type=str, help="Ruta del archivo Excel")
        parser.add_argument("--sheet", default="DIARIO", help="Nombre de la hoja (por defecto: DIARIO)")

    def handle(self, *args, **opts):
        ruta = opts["archivo"]
        hoja = opts["sheet"]

        # --- Leer hoja sin encabezado para encontrar la fila real ---
        try:
            raw = pd.read_excel(ruta, sheet_name=hoja, header=None, engine="openpyxl")
        except Exception as e:
            raise CommandError(f"No pude leer el archivo/hoja '{hoja}': {e}")

        # Detectar fila de cabecera (la que contiene “Folio”)
        header_row = None
        for idx in range(min(15, len(raw))):
            row_vals = [str(x).strip().lower() for x in raw.iloc[idx].tolist()]
            if any(val == "folio" for val in row_vals):
                header_row = idx
                break

        if header_row is None:
            raise CommandError("No encontré la fila de cabecera (columna 'Folio').")

        # --- Releer con esa fila como encabezado ---
        df = pd.read_excel(ruta, sheet_name=hoja, header=header_row, engine="openpyxl")
        df.columns = [norm(c) for c in df.columns]
        df = df.rename(columns={c: COLMAP.get(c, c) for c in df.columns})

        # --- (Opcional) Evitar crear filas totalmente vacías ---
        # Si quieres crear incluso las completamente vacías, comenta esta línea:
        df = df[~(df.get("monto").isna() & df.get("fecha").isna() & df.get("concepto").isna()
                  & df.get("programa").isna() & df.get("curp").isna() & df.get("nombre").isna()
                  & df.get("folio").isna())].copy()

        creados = 0

        # --- Procesar cada fila (SIEMPRE CREATE) ---
        with transaction.atomic():
            for _, r in df.iterrows():
                folio = folio_norm(r.get("folio"))  # puede ser None, numérico, o alfanumérico
                sede = s(r.get("sede"))
                nombre = s(r.get("nombre"))
                monto = d(r.get("monto"))
                grado = s(r.get("grado"))
                forma_pago = s(r.get("forma_pago") or r.get("forma_de_pago"))
                fecha = f(r.get("fecha"))           # date o None
                concepto = s(r.get("concepto"))
                pago_detalle = s(r.get("pago_detalle") or r.get("pago"))
                programa = s(r.get("programa"))
                no_auto = s(r.get("no_auto"))
                curp = s(r.get("curp"))
                if curp:
                    curp = curp.upper()
                numero_alumno = i(r.get("numero_alumno"))
                emision = s(r.get("emision"))

                alumno = None
                if numero_alumno:
                    alumno = Alumno.objects.filter(pk=numero_alumno).first()

                # Crear SIEMPRE (sin buscar existentes, sin actualizar)
                PagoDiario.objects.create(
                    folio=folio,
                    sede=sede,
                    nombre=nombre,
                    monto=monto,
                    grado=grado,
                    forma_pago=forma_pago,
                    fecha=fecha,
                    concepto=concepto,
                    pago_detalle=pago_detalle,
                    programa=programa,
                    no_auto=no_auto,
                    curp=curp,
                    emision=emision,
                    alumno=alumno,
                )
                creados += 1

        self.stdout.write(self.style.SUCCESS(
            f"✅ Pagos DIARIO importados (solo creación) -> creados: {creados}"
        ))

#python manage.py importar_pagos_diario "C:\Users\yatni\Downloads\copia IUAF Registro  de ingresos FINAL.xlsm" --sheet "DIARIO"