import re
import unicodedata

import pandas as pd
from django.core.management.base import BaseCommand
from django.db import transaction

# IMPORTA TUS MODELOS
from alumnos.models import Alumno, Pais, Programa, InformacionEscolar, Sede  # Estado lo dejamos en blanco por ahora
from decimal import Decimal
from datetime import datetime, date


def to_date(v):
    if v is None or (isinstance(v, float) and pd.isna(v)) or v == "":
        return None
    # pandas.Timestamp / datetime -> date
    if hasattr(v, "date"):
        try:
            return v.date()
        except Exception:
            pass
    # string ISO "YYYY-MM-DD" u otros
    try:
        return datetime.fromisoformat(str(v)).date()
    except Exception:
        return None


def to_decimal(v, default="0.00") -> Decimal:
    # Acepta números, strings tipo "2,275" o "$2,275.00", NaN, etc.
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


def to_int(v, default=0) -> int:
    if v is None or (isinstance(v, float) and pd.isna(v)) or v == "":
        return int(default)
    try:
        return int(str(v).strip())
    except Exception:
        try:
            # cuando viene "3.0" o "3,0"
            s = str(v).replace(",", "").strip()
            return int(float(s))
        except Exception:
            return int(default)


# ========= Utilidades de normalización =========
def norm(s: str) -> str:
    """
    Normaliza nombres de columna:
    - quita acentos
    - mayúsculas
    - colapsa espacios
    - quita puntos finales
    """
    if s is None:
        return ""
    s = str(s)
    s = ''.join(c for c in unicodedata.normalize('NFD', s)
                if unicodedata.category(c) != 'Mn')
    s = re.sub(r'\s+', ' ', s).strip().upper()
    s = s.rstrip('.')
    return s


def norm_text(s: str) -> str:
    """Normaliza texto libre tipo 'SEDE'."""
    if s is None:
        return ""
    s = ''.join(c for c in unicodedata.normalize('NFD', str(s))
                if unicodedata.category(c) != 'Mn')
    return re.sub(r'\s+', ' ', s).strip().upper()


# ========= Reglas de mapeo =========
# Si no es Panamá ni Guatemala, lo tratamos como México (para tus sedes listadas).
SEDE_PAISES_EXPL = {
    "PANAMA": "Panamá",
    "PANAMÁ": "Panamá",
    "GUATEMALA": "Guatemala",
}


def sede_a_pais_nombre(sede_raw: str) -> str:
    s = norm_text(sede_raw)
    if s in ("", "NA", "N/A"):
        return "México"
    if s in SEDE_PAISES_EXPL:
        return SEDE_PAISES_EXPL[s]
    # Tus sedes: Cancún, Puerto M, Kantunilkín, Ciudad del C, Chetumal, Toluca,
    # Chiapas, Monterrey, Saltillo => México
    return "México"


def get_pais(nombre: str) -> Pais:
    obj, _ = Pais.objects.get_or_create(nombre=nombre)
    return obj


def parse_fecha_nac_desde_curp(curp: str):
    """
    CURP estándar: 18 caracteres. YYMMDD en posiciones 5-10 (índices 4:10).
    Regla siglo: si YY <= año actual % 100 => 2000+YY, else 1900+YY.
    Si no se puede parsear, retorna None.
    """
    if not curp:
        return None
    curp = str(curp).strip().upper()
    if len(curp) < 10:
        return None
    try:
        yy = int(curp[4:6])
        mm = int(curp[6:8])
        dd = int(curp[8:10])
        current_two = date.today().year % 100
        year = 2000 + yy if yy <= current_two else 1900 + yy
        return date(year, mm, dd)
    except Exception:
        return None


def limpiar_telefono(s):
    s = str(s or "").strip()
    s = re.sub(r'[^\d+]', '', s)
    return s[:20]


def split_nombre_completo(fullname: str):
    """
    Formato de entrada (Excel): 
      PRIMER APELLIDO  SEGUNDO APELLIDO  NOMBRE(S)
    Heurística:
      - >=3 tokens: 0 -> apellido_p, 1 -> apellido_m, resto -> nombres
      - 2 tokens:   0 -> apellido_p, 1 -> nombres
      - 1 token:    nombres
    También normaliza a Título (Mayúscula inicial por palabra).
    """
    tokens = [t for t in str(fullname or "").strip().split() if t]

    apellido_p = ""
    apellido_m = ""
    nombres = ""

    if len(tokens) >= 3:
        apellido_p = tokens[0]
        apellido_m = tokens[1]
        nombres = " ".join(tokens[2:])
    elif len(tokens) == 2:
        apellido_p = tokens[0]
        apellido_m = ""
        nombres = tokens[1]
    elif len(tokens) == 1:
        nombres = tokens[0]
    else:
        return "", "", ""

    # Preserva partículas frecuentes en apellidos compuestos si venían separadas
    # (ej.: "DE", "DEL", "DE LA", "VAN", "VON") – sólo aplica cuando hay >=3 tokens.
    # Si quieres algo más elaborado, puedo añadir un parser con lista de partículas.
    def nice(x: str) -> str:
        x = x.lower()
        return " ".join(p.capitalize() for p in x.split())

    return nice(nombres), nice(apellido_p), nice(apellido_m)


def map_sexo(sexo_cell: str, curp: str):
    s = norm_text(sexo_cell)
    if s in ("H", "HOMBRE", "MASCULINO"):
        return "Hombre"
    if s in ("M", "MUJER", "FEMENINO"):
        return "Mujer"
    # Si no viene, intentar por CURP (posición 11 -> índice 10)
    if curp and len(curp) >= 11:
        ch = curp[10].upper()
        if ch == "H":
            return "Hombre"
        if ch == "M":
            return "Mujer"
    return ""  # vacío permitido en el modelo


# --- Normalización y mapeo de estatus a instancias ---
def norm_codigo_estatus(s: str) -> str:
    # "BAJA TEMPORAL" -> "BAJA_TEMPORAL", sin acentos, mayúsculas
    s = norm_text(s or "")
    s = s.replace(" ", "_")
    return s


# Sinónimos/fuzzy para ACADÉMICO
MAP_ACAD = {
    "VIGENTE": "VIGENTE",
    "EGRESADO": "EGRESADO",
    "EN_TITULACION": "EN_TITULACION",
    "EN_TITULACIÓN": "EN_TITULACION",
    "BAJA": "BAJA_TEMPORAL",          # ajusta a tu preferencia
    "BAJA_TEMPORAL": "BAJA_TEMPORAL",
    "BAJA_DEFINITIVA": "BAJA_DEFINITIVA",
}

# Sinónimos/fuzzy para ADMINISTRATIVO
MAP_ADMIN = {
    "VIGENTE": "VIGENTE",
    "EGRESADO": "EGRESADO",
    "BAJA": "BAJA_DEFINITIVA",        # ajusta a tu preferencia
    "BAJA_TEMPORAL": "BAJA_TEMPORAL",
    "BAJA_DEFINITIVA": "BAJA_DEFINITIVA",
}


def map_estatus_academico(texto: str):
    # import local para evitar dependencias en import-time
    from alumnos.models import EstatusAcademico
    cod_raw = norm_codigo_estatus(texto)
    if not cod_raw:
        return None
    # heurística por contenido
    if "DEFINIT" in cod_raw:
        cod = "BAJA_DEFINITIVA"
    elif "TEMP" in cod_raw:
        cod = "BAJA_TEMPORAL"
    elif "TITUL" in cod_raw:
        cod = "EN_TITULACION"
    else:
        cod = MAP_ACAD.get(cod_raw, cod_raw)
    obj, _ = EstatusAcademico.objects.get_or_create(
        codigo=cod,
        defaults={"nombre": cod.replace("_", " ")}
    )
    return obj


def map_estatus_administrativo(texto: str):
    from alumnos.models import EstatusAdministrativo
    cod_raw = norm_codigo_estatus(texto)
    if not cod_raw:
        return None
    if "DEFINIT" in cod_raw:
        cod = "BAJA_DEFINITIVA"
    elif "TEMP" in cod_raw:
        cod = "BAJA_TEMPORAL"
    else:
        cod = MAP_ADMIN.get(cod_raw, cod_raw)
    obj, _ = EstatusAdministrativo.objects.get_or_create(
        codigo=cod,
        defaults={"nombre": cod.replace("_", " ")}
    )
    return obj


class Command(BaseCommand):
    help = 'Importa alumnos desde Excel (hoja BASE ALUMNOS por defecto) y crea/actualiza en DB.'

    def add_arguments(self, parser):
        parser.add_argument('archivo', type=str, help='Ruta del archivo Excel (.xlsx/.xlsm)')
        parser.add_argument('--sheet', type=str, default='BASE ALUMNOS', help='Nombre de la hoja')

    def handle(self, *args, **options):
        archivo = options['archivo']
        sheet = options['sheet']

        # Campos objetivo (bonitos) -> clave normalizada
        objetivo = [
            "No.", "PROGRAMA", "CURP", "Matrícula Of. SEQ", "NOMBRE", "TELEFONO", "CORREO",
            "NO DE PAGOS (MESES)", "Meses de Programa", "INSCRIPCIÓN", "Reinscripcion",
            "Monto de Colegiatura (A PAGAR)", "Grupo de clase",
            "FECHA DE INICIO (PRIMERA CLASE CALENDARIO)", "Termina Programa",
            "Fecha Pago 1a Colegiatura", "Termina Pagos", "Sexo", "Grado", "SEDE", "SITUACIÓN",
            "Precio General", "Porcentaje de la Beca", "Monto del Descuento", "# Reinsc",
            "Equivalencia", "Titulación", "ESTATUS ACADÉMICO"
        ]
        objetivo_norm = {col: norm(col) for col in objetivo}

        try:
            # 1) Detectar fila de encabezado
            pre = pd.read_excel(archivo, sheet_name=sheet, header=None, nrows=50)
            header_row = None
            for i in range(len(pre)):
                fila_norm = [norm(x) for x in pre.iloc[i].tolist()]
                if any("NOMBRE" == x for x in fila_norm):
                    header_row = i
                    break
            if header_row is None:
                header_row = 0

            # 2) Leer con esa fila como header
            df = pd.read_excel(archivo, sheet_name=sheet, header=header_row)

            # 3) Normalizar columnas y mapear
            cols_orig = list(df.columns)
            cols_norm = [norm(c) for c in cols_orig]
            idx_map = {cols_norm[i]: cols_orig[i] for i in range(len(cols_norm))}

            # 4) Selección de columnas en el orden objetivo
            seleccion = []
            for bonito, clave_norm in objetivo_norm.items():
                if clave_norm in idx_map:
                    seleccion.append(idx_map[clave_norm])
            if not seleccion:
                self.stderr.write(self.style.ERROR(
                    "No se encontraron columnas que coincidan. Revisa los encabezados del archivo."
                ))
                self.stderr.write(f"Columnas detectadas: {cols_orig}")
                return
            df = df[seleccion]

            # 5) Filtrar filas sin NOMBRE
            col_nombre_real = idx_map.get(objetivo_norm["NOMBRE"])
            if col_nombre_real in df.columns:
                df = df[df[col_nombre_real].astype(str).str.strip().ne('')]
                df = df[df[col_nombre_real].notna()]

            # 6) Helpers locales
            def fmt(v):
                if pd.isna(v):
                    return ""
                return str(v).strip()

            # 7) Crear/actualizar alumnos
            created, updated, skipped, errores = 0, 0, 0, 0

            with transaction.atomic():
                for _, row in df.iterrows():
                    # ¿fila totalmente vacía?
                    if not any(fmt(row[c]) for c in seleccion):
                        continue

                    # Columnas que necesitamos
                    col_no = idx_map.get(objetivo_norm["No."])
                    col_nombre = idx_map.get(objetivo_norm["NOMBRE"])
                    col_curp = idx_map.get(objetivo_norm["CURP"])
                    col_tel = idx_map.get(objetivo_norm["TELEFONO"])
                    col_mail = idx_map.get(objetivo_norm["CORREO"])
                    col_sexo = idx_map.get(objetivo_norm["Sexo"]) if "Sexo" in objetivo_norm else None

                    col_sede = idx_map.get(objetivo_norm["SEDE"])

                    col_programa = idx_map.get(objetivo_norm["PROGRAMA"])
                    col_matricula = idx_map.get(objetivo_norm["Matrícula Of. SEQ"])
                    col_noPAGOS = idx_map.get(objetivo_norm["NO DE PAGOS (MESES)"])
                    col_meses_programa = idx_map.get(objetivo_norm["Meses de Programa"])
                    col_precio_inscripcion = idx_map.get(objetivo_norm["INSCRIPCIÓN"])
                    col_reinscripcion = idx_map.get(objetivo_norm["Reinscripcion"])
                    col_precio_colegiatura = idx_map.get(objetivo_norm["Monto de Colegiatura (A PAGAR)"])
                    col_grupoClase = idx_map.get(objetivo_norm["Grupo de clase"])
                    col_fechaInicioPrimeraClase = idx_map.get(objetivo_norm["FECHA DE INICIO (PRIMERA CLASE CALENDARIO)"])

                    col_fin_programa = idx_map.get(objetivo_norm["Termina Programa"])

                    col_fechaPagoprimeraColegiatura = idx_map.get(objetivo_norm["Fecha Pago 1a Colegiatura"])
                    col_terminaPago = idx_map.get(objetivo_norm["Termina Pagos"])
                    col_grado = idx_map.get(objetivo_norm["Grado"])
                    col_estatus_administrativo = idx_map.get(objetivo_norm["SITUACIÓN"])  # estado administrativo
                    col_precioGeneral = idx_map.get(objetivo_norm["Precio General"])
                    col_porcentajeBeca = idx_map.get(objetivo_norm["Porcentaje de la Beca"])
                    col_monto_descuento = idx_map.get(objetivo_norm["Monto del Descuento"])
                    col_numero_reinscripciones = idx_map.get(objetivo_norm["# Reinsc"])
                    col_precio_equivalencia = idx_map.get(objetivo_norm["Equivalencia"])
                    col_precio_titulacion = idx_map.get(objetivo_norm["Titulación"])
                    col_estatus_academico = idx_map.get(objetivo_norm["ESTATUS ACADÉMICO"])

                    numero_estudiante = fmt(row.get(col_no))
                    if not numero_estudiante:
                        skipped += 1
                        continue  # sin PK no podemos crear

                    nombre_completo = fmt(row.get(col_nombre))
                    curp_val = fmt(row.get(col_curp)).upper() or None  # se guarda aun si “falso”
                    telefono = limpiar_telefono(row.get(col_tel))
                    email = fmt(row.get(col_mail))
                    sexo_val = map_sexo(fmt(row.get(col_sexo)) if col_sexo else "", curp_val)
                    sede_val = fmt(row.get(col_sede))
                    programa_val = fmt(row.get(col_programa))

                    # País por sede
                    pais_nombre = sede_a_pais_nombre(sede_val)
                    pais_obj = get_pais(pais_nombre)

                    # Fecha de nacimiento si CURP válido, si no => None
                    fecha_nac = parse_fecha_nac_desde_curp(curp_val)

                    # Partir nombre completo
                    nombres, ape_p, ape_m = split_nombre_completo(nombre_completo)

                    sedes_obj = Sede.objects.filter(nombre=sede_val).first()
                    programa = Programa.objects.filter(codigo=programa_val).first()

                    try:
                        obj, was_created = Alumno.objects.update_or_create(
                            numero_estudiante=numero_estudiante,
                            defaults={
                                "nombre": nombres,
                                "apellido_p": ape_p,
                                "apellido_m": ape_m,
                                "email": email,
                                "telefono": telefono,
                                "curp": curp_val,              # puede repetirse entre alumnos (sin unique)
                                "pais": pais_obj,
                                "estado": None,                # por ahora sin estado
                                "fecha_nacimiento": fecha_nac, # None si no se derivó bien del CURP
                                "sexo": sexo_val,
                            }
                        )

                        # --- Campos de InformacionEscolar ---
                        precio_colegiatura_txt = fmt(row.get(col_precio_colegiatura))
                        monto_descuento_txt = fmt(row.get(col_monto_descuento))
                        meses_programa_val = to_int(row.get(col_meses_programa))
                        precio_inscripcion_txt = fmt(row.get(col_precio_inscripcion))
                        precio_titulacion_txt = fmt(row.get(col_precio_titulacion))
                        precio_equivalencia_txt = fmt(row.get(col_precio_equivalencia))
                        numero_reinscripciones_val = to_int(row.get(col_numero_reinscripciones))
                        fin_programa_txt = fmt(row.get(col_fin_programa))

                        estatus_academico_txt = fmt(row.get(col_estatus_academico))
                        estatus_administrativo_txt = fmt(row.get(col_estatus_administrativo))

                        # Mapear a instancias (crea si no existe)
                        ea = map_estatus_academico(estatus_academico_txt)
                        ed = map_estatus_administrativo(estatus_administrativo_txt)

                        fecha_alta_txt = fmt(row.get(col_fechaInicioPrimeraClase))
                        matricula = fmt(row.get(col_matricula))
                        grupo = fmt(row.get(col_grupoClase))

                        obj_infor = InformacionEscolar.objects.create(
                            programa=programa if programa else None,
                            precio_colegiatura=to_decimal(precio_colegiatura_txt),
                            monto_descuento=to_decimal(monto_descuento_txt),
                            meses_programa=meses_programa_val,                     # ENTERO
                            precio_inscripcion=to_decimal(precio_inscripcion_txt),
                            precio_titulacion=to_decimal(precio_titulacion_txt),
                            precio_equivalencia=to_decimal(precio_equivalencia_txt),
                            numero_reinscripciones=numero_reinscripciones_val,      # ENTERO
                            fecha_alta=to_date(fecha_alta_txt),
                            sede=sedes_obj,
                            precio_final=Decimal("450.00"),
                            fin_programa=to_date(fin_programa_txt),
                            grupo=grupo,
                            modalidad="en_linea",
                            matricula=matricula,
                            estatus_academico=ea,            # INSTANCIA
                            estatus_administrativo=ed,       # INSTANCIA
                        )

                        # ENLACE OneToOne (indispensable)
                        obj.informacionEscolar = obj_infor
                        obj.save(update_fields=["informacionEscolar"])

                        if was_created:
                            created += 1
                        else:
                            updated += 1

                    except Exception as e:
                        errores += 1
                        self.stderr.write(self.style.ERROR(
                            f"[Alumno {numero_estudiante}] Error: {e}"
                        ))

            self.stdout.write(self.style.SUCCESS(
                f"Alumnos -> creados: {created}, actualizados: {updated}, omitidos: {skipped}, errores: {errores}"
            ))

        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Error leyendo el archivo: {e}"))

# Ejemplo:
#python manage.py seed_conceptos_pago
#python manage.py crear_sedes
#python manage.py cargar_programas
#python manage.py crear_grupos_basicos
#python manage.py init_roles
#python manage.py importar_alumnosV2 "C:\Users\yatni\Downloads\COPIA control alumnos totales 2022.xlsm"
#python manage.py importar_pagos_diario "C:\Users\yatni\Downloads\copia IUAF Registro  de ingresos FINAL.xlsm" --sheet "DIARIO"
#python manage.py seed_documentos

