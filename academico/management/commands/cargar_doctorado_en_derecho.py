# academico/management/commands/cargar_dd_materias.py
from django.core.management.base import BaseCommand, CommandError
from academico.models import Materia
from alumnos.models import Programa

MATERIAS_DD = [
    # --- 1er cuatrimestre ---
    ("DD01",   "Seminario de Filosofía Jurídica"),
    ("DD04",   "Seminario de Juicio Oral Familiar"),
    ("DD05-1", "Seminario de Gestión de Conflictos"),
    ("DD05-2", "Seminario de Solución de Conflictos y Justicia Restaurativa"),
    # --- 2º cuatrimestre ---
    ("DD06-1", "Seminario de Juicio Oral Civil, Mercantil"),
    ("DD15",   "Seminario de Tesis"),
    ("DD10",   "Clínica de Derecho Procesal Laboral"),
    ("DD06-2", "Seminario de Justicia para Adolescentes"),
    # --- 3er cuatrimestre ---
    ("DD09-I",  "Clínica de Estrategias del Proceso Penal I"),
    ("DD09-II", "Clínica de Estrategias del Proceso Penal II"),
    ("DD08",    "Clínica de Derecho Procesal Civil"),
    ("DD02",    "Seminario de Interpretación y Metodología Jurídica"),
    # --- 4º cuatrimestre ---
    ("DD14-I",  "Seminario de Derecho Societario y Corporativo I"),
    ("DD14-II", "Seminario de Derecho Societario y Corporativo II"),
    ("DD12",    "Seminario de Derecho Aduanero y Comercio Exterior"),
    ("DD13-I",  "Seminario de Derecho Fiscal I"),
    # --- 5º cuatrimestre ---
    ("DD13-II", "Seminario de Derecho Fiscal II"),
    ("DD07",    "Seminario de Investigación: Género y Derecho"),
    ("DD11-I",  "Seminario de Derecho Procesal de Amparo I"),
    ("DD11-II", "Seminario de Derecho Procesal de Amparo II"),
]

class Command(BaseCommand):
    help = "Crea/actualiza las materias del Doctorado en Derecho dentro de un Programa."

    def add_arguments(self, parser):
        parser.add_argument(
            "--programa-codigo",
            help="Código del programa (ej. 'DD'). Si se omite, intenta encontrar 'Doctorado en Derecho'.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Muestra lo que haría sin escribir en la base de datos",
        )

    def _resolver_programa(self, programa_codigo: str | None) -> Programa:
        if programa_codigo:
            try:
                return Programa.objects.get(codigo__iexact=programa_codigo.strip())
            except Programa.DoesNotExist:
                raise CommandError(f"No existe Programa con código '{programa_codigo}'.")
            except Programa.MultipleObjectsReturned:
                raise CommandError(f"Hay múltiples Programas con código '{programa_codigo}'.")
        # Auto: busca por nombre “Doctorado en Derecho”; si no, intenta por código 'DD'
        qs = Programa.objects.filter(nombre__iexact="Doctorado en Derecho")
        if not qs.exists():
            qs = Programa.objects.filter(nombre__icontains="Doctorado en Derecho")
        if qs.count() == 1:
            return qs.first()
        if qs.count() > 1:
            raise CommandError("Hay múltiples Programas cuyo nombre coincide con 'Doctorado en Derecho'. Usa --programa-codigo.")
        # último intento: código 'DD'
        try:
            return Programa.objects.get(codigo__iexact="DD")
        except Programa.DoesNotExist:
            raise CommandError(
                "No encontré el Programa de Doctorado en Derecho. "
                "Indica uno con --programa-codigo=DD (o el que corresponda)."
            )

    def handle(self, *args, **opts):
        programa = self._resolver_programa(opts.get("programa_codigo"))
        self.stdout.write(self.style.HTTP_INFO(f"Programa objetivo: {programa.codigo} — {programa.nombre}"))

        created, updated = 0, 0
        for codigo, nombre in MATERIAS_DD:
            if opts["dry_run"]:
                self.stdout.write(f"[dry-run] ({programa.codigo}) {codigo:<8} {nombre}")
                continue

            obj, was_created = Materia.objects.update_or_create(
                programa=programa,
                codigo=codigo,
                defaults={"nombre": nombre},
            )
            if was_created:
                created += 1
                self.stdout.write(self.style.SUCCESS(f"✓ Creada      {programa.codigo}:{codigo} — {nombre}"))
            else:
                updated += 1
                self.stdout.write(self.style.WARNING(f"• Actualizada {programa.codigo}:{codigo} — {nombre}"))

        if not opts["dry_run"]:
            self.stdout.write(self.style.MIGRATE_HEADING(
                f"Resumen: {created} creadas, {updated} actualizadas (total {created+updated})"
            ))

#python manage.py cargar_doctorado_en_derecho --programa-codigo=DD
