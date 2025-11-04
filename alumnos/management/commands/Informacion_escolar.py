import re
import unicodedata
from datetime import datetime
from decimal import Decimal

import pandas as pd
from django.core.management.base import BaseCommand
from django.db import transaction

from alumnos.models import (
    Alumno, Programa, Financiamiento,
    InformacionEscolar, Sede, Pais
)

# ---------- helpers ----------
def norm(s: str) -> str:
    if s is None: return ""
    s = str(s)
    s = ''.join(c for c in unicodedata.normalize('NFD', s)
                if unicodedata.category(c) != 'Mn')
    s = re.sub(r'\s+', ' ', s).strip().upper()
    return s.rstrip('.')

def fmt(v):
    if pd.isna(v): return ""
    return str(v).strip()

def to_decimal(v, default="0.00"):
    if v is None or v == "" or (isinstance(v, float) and pd.isna(v)):
        return Decimal(default)
    try:
        return Decimal(str(v)).quantize(Decimal("0.01"))
    except Exception:
        try:
            s = str(v).replace(",", "").replace("$", "").strip()
            return Decimal(s).quantize(Decimal("0.01"))
        except Exception:
            return Decimal(default)

def to_int(v, default=0):
    try:
        if v is None or v == "" or (isinstance(v, float) and pd.isna(v)):
            return default
        return int(float(v))
    except Exception:
        return default

def to_date(v):
    """ Devuelve date o None (acepta pandas.Timestamp, datetime, 'YYYY-MM-DD', etc.). """
    if v is None or v == "" or (isinstance(v, float) and pd.isna(v)):
        return None
    # pandas.Timestamp o datetime
    if hasattr(v, "date"):
        try:
            return v.date()
        except Exception:
            pass
    # cadena ISO
    try:
        return datetime.fromisoformat(str(v)).date()
    except Exception:
        return None

def coerce_num_est(v: str) -> str:
    s = ("" if v is None else str(v)).strip()
    if s == "": return ""
    try:
        f = float(s)
        if f.is_integer():
            return str(int(f))
    except Exception:
        pass
    return s

SEDE_PAISES_EXPL = {"PANAMA": "Panamá", "PANAMÁ": "Panamá", "GUATEMALA": "Guatemala"}

def sede_a_pais_nombre(sede_raw: str) -> str:
    s = norm(sede_raw)
    if s in ("", "NA", "N/A"): return "México"
    if s in SEDE_PAISES_EXPL:  return SEDE_PAISES_EXPL[s]
    return "México"

def get_pais(nombre: str) -> Pais:
    obj, _ = Pais.objects.get_or_create(nombre=nombre)
    return obj

def get_sede(nombre_sede: str):
    nombre = fmt(nombre_sede)
    if not nombre:
        return None
    pais = get_pais(sede_a_pais_nombre(nombre))
    sede, _ = Sede.objects.get_or_create(
        nombre=nombre, pais=pais, defaults={"estado": None, "activo": True}
    )
    return sede

def build_or_get_financiamiento(porcentaje_beca, etiqueta_default=""):
    try:
        p = Decimal(str(porcentaje_beca))
        if p > 0 and p <= 1:
            label = f"Beca {round(p*100)}%"
        elif p > 1 and p <= 100:
            label = f"Beca {round(p)}%"
        else:
            label = etiqueta_default.strip() if etiqueta_default else ""
    except Exception:
        label = etiqueta_default.strip() if etiqueta_default else ""
    if not label:
        return None
    obj, _ = Financiamiento.objects.get_or_create(beca=label)
    return obj


class Command(BaseCommand):
    help = "Importa/actualiza InformacionEscolar desde la hoja BASE ALUMNOS."

    def add_arguments(self, parser):
        parser.add_argument("archivo", type=str, help="Ruta del Excel (.xlsx/.xlsm)")
        parser.add_argument("--sheet", type=str, default="BASE ALUMNOS")

    def handle(self, *args, **options):
        archivo = options["archivo"]
        sheet = options["sheet"]

        objetivo = [
            "No.", "PROGRAMA", "NO DE PAGOS (MESES)", "Meses de Programa",
            "INSCRIPCIÓN", "Reinscripcion", "Monto de Colegiatura (A PAGAR)",
            "FECHA DE INICIO (PRIMERA CLASE CALENDARIO)", "Termina Programa",
            "Fecha Pago 1a Colegiatura", "Termina Pagos",
            "SEDE", "Grupo de clase",
            "Matrícula Of. SEQ",
            "ESTATUS ACADÉMICO", "SITUACIÓN",
            "Precio General", "Porcentaje de la Beca", "Monto del Descuento",
            "Equivalencia", "Titulación", "# Reinsc"
        ]
        objetivo_norm = {col: norm(col) for col in objetivo}

        try:
            # 1) Detecta header buscando fila con "PROGRAMA" o "NOMBRE"
            pre = pd.read_excel(archivo, sheet_name=sheet, header=None, nrows=80)
            header_row = None
            for i in range(len(pre)):
                fila_norm = [norm(x) for x in pre.iloc[i].tolist()]
                if "PROGRAMA" in fila_norm or "NOMBRE" in fila_norm:
                    header_row = i
                    break
            if header_row is None:
                header_row = 0

            # 2) Leer con esa fila como header
            df = pd.read_excel(archivo, sheet_name=sheet, header=header_row)

            # 3) Normalizar y mapear columnas
            cols_orig = list(df.columns)
            cols_norm = [norm(c) for c in cols_orig]
            idx_map = {cols_norm[i]: cols_orig[i] for i in range(len(cols_norm))}

            # 4) Encontrar columna No. de forma robusta
            no_aliases = ["No.", "No", "N°", "Nº", "Numero", "Número", "#", "ID", "Id"]
            col_no = None
            for cand in no_aliases:
                k = norm(cand)
                if k in idx_map:
                    col_no = idx_map[k]
                    break
            if not col_no:
                self.stderr.write(self.style.ERROR(
                    "No se encontró la columna de número de estudiante (No./ID)."
                ))
                self.stderr.write(f"Encabezados normalizados: {cols_norm}")
                return

            # 5) Reducir DataFrame a las columnas disponibles
            seleccion = [idx_map[v] for v in objetivo_norm.values() if v in idx_map]
            if col_no not in seleccion:
                seleccion = [col_no] + seleccion
            df = df[seleccion]

            created, updated, skipped, not_found_alumno, not_found_program, errores = 0, 0, 0, 0, 0, 0

            with transaction.atomic():
                for _, row in df.iterrows():
                    # --- PK alumno ---
                    numero_estudiante = coerce_num_est(fmt(row.get(col_no)))
                    if not numero_estudiante:
                        skipped += 1
                        continue

                    try:
                        alumno = Alumno.objects.select_for_update().get(numero_estudiante=numero_estudiante)
                    except Alumno.DoesNotExist:
                        not_found_alumno += 1
                        continue

                    # --- valores por fila (¡no los nombres de columna!) ---
                    col_prog = idx_map.get(objetivo_norm["PROGRAMA"])
                    prog_codigo = norm(row.get(col_prog)) if col_prog in df.columns else ""
                    if not prog_codigo:
                        not_found_program += 1
                        continue
                    try:
                        programa = Programa.objects.get(codigo=prog_codigo)
                    except Programa.DoesNotExist:
                        not_found_program += 1
                        continue

                    col_meses = idx_map.get(objetivo_norm["Meses de Programa"])
                    col_meses_alt = idx_map.get(objetivo_norm["NO DE PAGOS (MESES)"])
                    meses_programa = to_int(row.get(col_meses)) if col_meses in df.columns else to_int(row.get(col_meses_alt))

                    col_insc = idx_map.get(objetivo_norm["INSCRIPCIÓN"])
                    col_colegiatura = idx_map.get(objetivo_norm["Monto de Colegiatura (A PAGAR)"])
                    col_equiv = idx_map.get(objetivo_norm["Equivalencia"])
                    col_titul = idx_map.get(objetivo_norm["Titulación"])
                    precio_inscripcion  = to_decimal(row.get(col_insc), "0.00") if col_insc in df.columns else Decimal("0.00")
                    precio_colegiatura  = to_decimal(row.get(col_colegiatura), "0.00") if col_colegiatura in df.columns else Decimal("0.00")
                    precio_equivalencia = to_decimal(row.get(col_equiv), "-1.00") if col_equiv in df.columns else Decimal("-1.00")
                    precio_titulacion   = to_decimal(row.get(col_titul), "0.00") if col_titul in df.columns else Decimal("0.00")

                    col_desc = idx_map.get(objetivo_norm["Monto del Descuento"])
                    monto_descuento = to_decimal(row.get(col_desc), "0.00") if col_desc in df.columns else Decimal("0.00")

                    col_reinscs = idx_map.get(objetivo_norm["# Reinsc"])
                    numero_reinscripciones = to_int(row.get(col_reinscs), 0) if col_reinscs in df.columns else 0

                    col_fin_prog = idx_map.get(objetivo_norm["Termina Programa"])
                    fin_programa = to_date(row.get(col_fin_prog)) if col_fin_prog in df.columns else None

                    col_sede = idx_map.get(objetivo_norm["SEDE"])
                    sede = get_sede(row.get(col_sede)) if col_sede in df.columns else None

                    col_grupo = idx_map.get(objetivo_norm["Grupo de clase"])
                    grupo = fmt(row.get(col_grupo)) if col_grupo in df.columns else ""

                    col_mat = idx_map.get(objetivo_norm["Matrícula Of. SEQ"])
                    matricula = fmt(row.get(col_mat)) if col_mat in df.columns else ""

                    col_est_acad = idx_map.get(objetivo_norm["ESTATUS ACADÉMICO"])
                    estatus_acad = fmt(row.get(col_est_acad)) if col_est_acad in df.columns else ""

                    col_situacion = idx_map.get(objetivo_norm["SITUACIÓN"])
                    estatus_admin = fmt(row.get(col_situacion)) if col_situacion in df.columns else ""

                    # Financiamiento (opcional; crea etiqueta si hay porcentaje)
                    col_porc_beca = idx_map.get(objetivo_norm["Porcentaje de la Beca"])
                    porc_beca_val = row.get(col_porc_beca) if col_porc_beca in df.columns else None
                    financiamiento = build_or_get_financiamiento(porc_beca_val, etiqueta_default="")

                    # --- crear/actualizar IE del alumno ---
                    try:
                        # Si ya tiene IE, la actualizamos; si no, creamos una y la enganchamos al alumno.
                        ie = alumno.informacionEscolar if alumno.informacionEscolar_id else InformacionEscolar()

                        ie.programa = programa
                        ie.financiamiento = financiamiento
                        ie.precio_colegiatura = precio_colegiatura
                        ie.monto_descuento = monto_descuento
                        ie.meses_programa = meses_programa
                        ie.precio_inscripcion = precio_inscripcion
                        ie.precio_titulacion = precio_titulacion
                        ie.precio_equivalencia = precio_equivalencia
                        ie.numero_reinscripciones = numero_reinscripciones
                        ie.sede = sede
                        ie.fin_programa = fin_programa  # None si no hay fecha válida
                        ie.grupo = grupo or ""
                        ie.modalidad = "en_linea"
                        ie.matricula = matricula or ""
                        ie.estatus_academico = estatus_acad or ""
                        ie.estatus_administrativo = estatus_admin or ""
                        ie.precio_final = None  # deja que save() lo calcule si procede
                        ie.save()

                        if not alumno.informacionEscolar_id:
                            alumno.informacionEscolar = ie
                            alumno.save(update_fields=["informacionEscolar"])
                            created += 1
                        else:
                            updated += 1

                    except Exception as e:
                        errores += 1
                        self.stderr.write(self.style.ERROR(f"[Alumno {numero_estudiante}] Error IE: {e}"))
                        continue

            self.stdout.write(self.style.SUCCESS(
                "InformacionEscolar -> "
                f"creadas: {created}, actualizadas: {updated}, "
                f"omitidos (sin No.): {skipped}, sin alumno: {not_found_alumno}, "
                f"sin programa: {not_found_program}, errores: {errores}"
            ))

        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Error leyendo el archivo: {e}"))


#python manage.py Informacion_escolar "C:\Users\yatni\Downloads\COPIA control alumnos totales 2022.xlsm"