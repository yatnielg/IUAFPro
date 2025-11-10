# academico/management/commands/seed_academico.py
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from datetime import date, timedelta
import random

from alumnos.models import Alumno, Programa
from academico.models import Materia, ListadoMaterias, ListadoMateriaItem, ListadoAlumno

def parse_alumnos_selector(sel: str):
    """
    Convierte '870-875,901,903-904' -> ['870','871','872','873','874','875','901','903','904']
    No hace padding; compara como string (coincide con numero_estudiante si es CharField).
    """
    if not sel:
        return []
    result = []
    for chunk in sel.split(","):
        s = chunk.strip()
        if not s:
            continue
        if "-" in s:
            a, b = s.split("-", 1)
            try:
                ai = int(a.strip()); bi = int(b.strip())
            except ValueError:
                # si no son números, añade literal
                result.append(s)
            else:
                if ai <= bi:
                    result.extend([str(x) for x in range(ai, bi+1)])
                else:
                    result.extend([str(x) for x in range(bi, ai+1)])
        else:
            result.append(s)
    # únicos y en orden de aparición
    seen = set(); out = []
    for v in result:
        if v not in seen:
            out.append(v); seen.add(v)
    return out

class Command(BaseCommand):
    help = "Genera datos de ejemplo para academico (materias, listados e inscripciones)."

    def add_arguments(self, parser):
        parser.add_argument("--programa", required=True, help="Código del Programa (ej. LD)")
        parser.add_argument("--materias", type=int, default=5, help="Cuántas materias crear por listado")
        parser.add_argument("--listados", type=int, default=1, help="Cuántos listados crear")
        parser.add_argument("--prefix", default="Cohorte Demo", help="Prefijo para el nombre del listado")
        parser.add_argument("--alumnos", default="", help="Filtro de alumnos por numero_estudiante. Ej: '870-875,901'")

    @transaction.atomic
    def handle(self, *args, **opts):
        prog_code = opts["programa"]
        n_mats    = opts["materias"]
        n_lists   = opts["listados"]
        prefix    = opts["prefix"]
        sel       = opts["alumnos"]

        prog = Programa.objects.filter(codigo=prog_code).first()
        if not prog:
            raise CommandError(f"No existe Programa con codigo='{prog_code}'")

        # --- Selección de alumnos ---
        qs_alumnos = Alumno.objects.filter(informacionEscolar__programa=prog).select_related("informacionEscolar")
        wanted = parse_alumnos_selector(sel)
        if wanted:
            # numero_estudiante suele ser CharField: filtra por lista de strings
            qs_alumnos = qs_alumnos.filter(numero_estudiante__in=wanted)

        alumnos = list(qs_alumnos.order_by("pk"))
        if not alumnos:
            msg = "No se encontraron alumnos del programa"
            if wanted:
                msg += f" con numero_estudiante en {wanted}"
            raise CommandError(msg + ".")

        self.stdout.write(self.style.NOTICE("Alumnos seleccionados: " + ", ".join(str(a.numero_estudiante) for a in alumnos)))


        # --- Crear materias base (si no hay suficientes) ---
        base_cod = ["MAT", "INF", "ADM", "COM", "LEG", "FIN", "EST", "PSI", "SOC", "HIS"]
        creadas_mats = 0
        while Materia.objects.count() < n_mats:
            idx = Materia.objects.count() + 1
            codigo = f"{random.choice(base_cod)}{idx:03d}"
            Materia.objects.get_or_create(
                codigo=codigo,
                defaults={"nombre": f"Materia {codigo}"}
            )
            creadas_mats += 1

        materias = list(Materia.objects.all().order_by("codigo")[:n_mats])
        self.stdout.write(self.style.SUCCESS(f"Materias disponibles: {len(materias)} (creadas ahora: {creadas_mats})."))

        # --- Generar listados ---
        hoy = date.today()
        for i in range(1, n_lists + 1):
            nombre_listado = f"{prefix} #{i}"
            lm, created = ListadoMaterias.objects.get_or_create(
                programa=prog,
                nombre=nombre_listado,
                defaults={"descripcion": f"Listado de ejemplo {i} para {prog.codigo}"}
            )
            self.stdout.write(self.style.NOTICE(f"{'Creado' if created else 'Usado'}: {lm}"))

            # Items (materias con fechas)
            # Ventanas de 6 semanas por materia, escalonadas
            base_start = hoy + timedelta(days=7*i)
            creados_items = 0
            for idx, m in enumerate(materias, start=1):
                fi = base_start + timedelta(days=7*(idx-1))
                ff = fi + timedelta(days=42)  # 6 semanas
                obj, it_created = ListadoMateriaItem.objects.update_or_create(
                    listado=lm, materia=m,
                    defaults={"fecha_inicio": fi, "fecha_fin": ff}
                )
                if it_created:
                    creados_items += 1

            # Inscribir alumnos seleccionados
            creadas_ins = 0
            for a in alumnos:
                ListadoAlumno.objects.get_or_create(listado=lm, alumno=a)
                creadas_ins += 1

            self.stdout.write(self.style.SUCCESS(
                f"Listado '{lm.nombre}': items nuevos {creados_items}, alumnos añadidos {creadas_ins}."
            ))

        self.stdout.write(self.style.SUCCESS("Seed terminado."))

