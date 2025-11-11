# academico/management/commands/cargar_mdp_materias.py
from django.core.management.base import BaseCommand, CommandError
from academico.models import Materia
from alumnos.models import Programa

"""
Carga el catálogo de materias de la Maestría en Derecho Procesal Penal y Juicios Orales (MDP).
Basado en los planes y fechas mostrados en las imágenes.

Notas:
- Se agregan sufijos (-I, -II) cuando una materia se repite con distinto nivel.
- Si el código de Programa en tu base no es 'MDP', puedes especificarlo con --programa-codigo.
"""

MATERIAS_MDP = [
    # ---------- PRIMER CUATRIMESTRE ----------
    ("MDP10-II", "Impugnación y Sistema Internacional de Protección de Derechos Humanos II"),
    ("MDP05",    "Teoría del Caso"),
    ("MDP12",    "Sistemas Actuales del Proceso Penal"),
    ("MDP07-I",  "Amparo Penal I"),

    # ---------- SEGUNDO CUATRIMESTRE ----------
    ("MDP07-II", "Amparo Penal II"),
    ("MDP01",    "Sistema de Justicia Penal en México"),
    ("MDP04-I",  "Técnicas, Actos y Medios de Investigación I"),
    ("MDP04-II", "Técnicas, Actos y Medios de Investigación II"),

    # ---------- TERCER CUATRIMESTRE ----------
    ("MDP08",    "Formalidades y Procedimientos en las Audiencias: Inicial, Intermedia y Debate"),
    ("MDP02",    "Argumentación Jurídica"),
    ("MDP06",    "Obtención y Medios de Prueba"),
    ("MDP09",    "Ejecución de Penas"),

    # ---------- CUARTO CUATRIMESTRE ----------
    ("MDP12-RA", "Retórica Argumentativa"),
    ("MDP03",    "Derecho Procesal Acusatorio"),
    ("MDP13",    "Mecanismos de Medios de Solución de Conflictos"),
    ("MDP10-I",  "Impugnación y Sistema Internacional de Protección de Derechos Humanos I"),
]

class Command(BaseCommand):
    help = "Crea/actualiza las materias de la Maestría en Derecho Procesal Penal y Juicios Orales (MDP)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--programa-codigo",
            help="Código del programa (por defecto: 'MDP').",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Simula la carga sin modificar la base de datos.",
        )

    def _resolver_programa(self, programa_codigo: str | None) -> Programa:
        codigo = programa_codigo or "MDP"
        try:
            return Programa.objects.get(codigo__iexact=codigo.strip())
        except Programa.DoesNotExist:
            raise CommandError(f"No existe un Programa con código '{codigo}'.")
        except Programa.MultipleObjectsReturned:
            raise CommandError(f"Existen múltiples programas con código '{codigo}', especifique uno exacto.")

    def handle(self, *args, **opts):
        programa = self._resolver_programa(opts.get("programa_codigo"))
        self.stdout.write(self.style.HTTP_INFO(f"Programa objetivo: {programa.codigo} — {programa.nombre}"))

        created, updated = 0, 0
        for codigo, nombre in MATERIAS_MDP:
            if opts["dry_run"]:
                self.stdout.write(f"[dry-run] ({programa.codigo}) {codigo:<10} {nombre}")
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
#python manage.py cargar_mdp_materias --programa-codigo=MDP
