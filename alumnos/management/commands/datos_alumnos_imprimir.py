import pandas as pd
import re
import unicodedata
from django.core.management.base import BaseCommand

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
    # a str
    s = str(s)
    # quitar acentos
    s = ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')
    # mayúsculas y colapsar espacios
    s = re.sub(r'\s+', ' ', s).strip().upper()
    # quitar puntos al final tipo "No."
    s = s.rstrip('.')
    return s

class Command(BaseCommand):
    help = 'Lee la hoja BASE ALUMNOS del Excel y muestra los datos en consola (robusto)'

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
            # 1) Detectar fila de encabezado (leer sin header y buscar la fila que contenga "NOMBRE")
            pre = pd.read_excel(archivo, sheet_name=sheet, header=None, nrows=50)
            header_row = None
            for i in range(len(pre)):
                fila_norm = [norm(x) for x in pre.iloc[i].tolist()]
                if any("NOMBRE" == x for x in fila_norm):
                    header_row = i
                    break

            if header_row is None:
                # Si no se encontró, tomamos la primera fila como encabezado
                header_row = 0

            # 2) Leer de nuevo usando esa fila como header
            df = pd.read_excel(archivo, sheet_name=sheet, header=header_row)

            # 3) Normalizar columnas y crear un mapeo original->bonito
            cols_orig = list(df.columns)
            cols_norm = [norm(c) for c in cols_orig]

            # Mapa de columna normalizada -> índice original
            idx_map = {cols_norm[i]: cols_orig[i] for i in range(len(cols_norm))}

            # Construir lista de columnas a usar en el orden objetivo
            seleccion = []
            encabezados_para_imprimir = []
            for bonito, clave_norm in objetivo_norm.items():
                if clave_norm in idx_map:
                    seleccion.append(idx_map[clave_norm])
                    encabezados_para_imprimir.append(bonito)  # conservamos el nombre "bonito"

            if not seleccion:
                self.stderr.write(self.style.ERROR(
                    "No se encontraron columnas que coincidan. "
                    "Revisa los encabezados del archivo."
                ))
                # Imprimir columnas detectadas para depurar
                self.stderr.write(f"Columnas detectadas: {cols_orig}")
                return

            df = df[seleccion]

            # 4) Filtrar filas sin NOMBRE
            col_nombre_real = idx_map.get(objetivo_norm["NOMBRE"])
            if col_nombre_real in df.columns:
                df = df[df[col_nombre_real].astype(str).str.strip().ne('')]
                df = df[df[col_nombre_real].notna()]

            # 5) Imprimir filas (saltando completamente vacías)
            def fmt(v):
                if pd.isna(v):
                    return ""
                return str(v).strip()

            for _, row in df.iterrows():
                # ¿hay algo que imprimir?
                valores = [fmt(row[c]) for c in seleccion]
                if not any(valores):  # todo vacío
                    continue

                print("\n---------------------------")           
                for bonito, col_real in zip(encabezados_para_imprimir, seleccion):                    
                    val = fmt(row[col_real])
                    # si quieres omitir campos vacíos, descomenta:
                    # if val == "":
                    #     continue                    
                    print(f"{bonito}: {val}")

        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Error leyendo el archivo: {e}"))
