from django.core.management import BaseCommand, CommandError
from decimal import Decimal
from alumnos.models import Programa
import re

TEXTO = """
Programas	Nombre de Cursos	Meses Programa	Colegiatura	Inscripción	Reinscripción	Equivalencia	Titulación
LD	LICENCIATURA EN DERECHO	36	$3,150.00	$1,000.00	$1,000.00	$0.00	$23,000.00
MD	MAESTRÍA EN DERECHO	20	$5,000.00	$1,000.00	$0.00	$0.00	$26,000.00
DD	DOCTORADO EN DERECHO	20	$7,000.00	$3,000.00	$3,000.00	$0.00	$29,000.00
DIAP	DOCTORADO EN INNOVACIÓN, ADMÓN. Y POLITICAS PÚBLICAS	20	$7,000.00	$3,000.00	$3,000.00	$0.00	$29,000.00
JTLD	JT DE LICENCIATURA EN DERECHO	8	$5,000.00	$1,000.00	$0.00	$5,000.00	$23,000.00
JTMD	JT MAESTRÍA EN DERECHO	6	$5,000.00	$2,000.00	$0.00	$6,000.00	$26,000.00
JTDD	JT DOCTORADO EN DERECHO	6	$7,000.00	$3,000.00	$0.00	$8,000.00	$29,000.00
MDP	MAESTRÍA EN DERECHO PROCESAL PENAL Y JUICIOS ORALES	16	$5,000.00	$2,000.00	$2,000.00	$0.00	$26,000.00
JTMDP	JT MAESTRIA EN DERECHO PROCESAL PENAL Y JUICIOS ORALES	6	$5,000.00	$2,000.00	$0.00	$6,000.00	$26,000.00
JTDIAP	JT DOCTORADO EN INNOVACIÓN, ADMÓN. Y POLITICAS PÚBLICAS	6	$7,000.00	$3,000.00	$0.00	$8,000.00	$29,000.00
CADP	DIPLOMADO	6	$2,275.00	$2,000.00	$0.00	$0.00	$0.00
DIP IA	DIPLOMADO INT ARTIFICIAL	6	$3,000.00	$1,000.00	$0.00	$0.00	$0.00
TU	TALLER UNICO 	1	$2,400.00	$0.00	$0.00	$0.00	$0.00
ACT DER	ACTUALIZACION DERECHO	36	$3,150.00	$1,000.00	$1,000.00	$0.00	$21,000.00
CU	CERTIFICACION UNIVERSITARIA	1	$2,400.00	$0.00	$0.00	$0.00	$0.00
DDG	DOCTORADO EN DERECHO	20	$7,500.00	$7,000.00	$1,000.00	$0.00	$30,000.00
""".strip()

def parse_money(s: str) -> Decimal:
    if s is None:
        return Decimal("0")
    s = s.strip()
    # Elimina $ y comas, respeta decimales
    s = s.replace("$", "").replace(",", "")
    if s == "":
        return Decimal("0")
    return Decimal(s)

class Command(BaseCommand):
    help = "Carga/actualiza el catálogo de Programas desde el bloque TAB separado."

    def handle(self, *args, **kwargs):
        lineas = [ln for ln in TEXTO.splitlines() if ln.strip()]
        if not lineas or "Programas" not in lineas[0]:
            raise CommandError("Encabezado inválido. Debe iniciar con 'Programas\\tNombre de Cursos...'")

        creados, actualizados = 0, 0
        for ln in lineas[1:]:
            cols = ln.split("\t")
            if len(cols) < 8:
                self.stdout.write(self.style.WARNING(f"Fila ignorada (faltan columnas): {ln}"))
                continue

            codigo = cols[0].strip()
            nombre = cols[1].strip()
            try:
                meses = int(cols[2].strip())
            except ValueError:
                self.stdout.write(self.style.WARNING(f"Meses inválidos en fila: {ln}"))
                continue

            colegiatura = parse_money(cols[3])
            inscripcion = parse_money(cols[4])
            reinscripcion = parse_money(cols[5])
            equivalencia = parse_money(cols[6])
            titulacion = parse_money(cols[7])

            obj, created = Programa.objects.update_or_create(
                codigo=codigo,
                defaults={
                    "nombre": nombre,
                    "meses_programa": meses,
                    "colegiatura": colegiatura,
                    "inscripcion": inscripcion,
                    "reinscripcion": reinscripcion,
                    "equivalencia": equivalencia,
                    "titulacion": titulacion,
                    "activo": True,
                }
            )
            creados += int(created)
            actualizados += int(not created)

        self.stdout.write(self.style.SUCCESS(f"Listo: Programas creados {creados}, actualizados {actualizados}."))
