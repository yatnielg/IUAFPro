# academico/management/commands/cargar_diap_materias.py
from django.core.management.base import BaseCommand, CommandError
from academico.models import Materia
from alumnos.models import Programa

# Catálogo de materias según el plan mostrado en las fotos
# Nota: cuando una misma clave "oficial" abarca dos asignaturas (I/II),
# usamos sufijos "-I" y "-II" para mantener códigos únicos.
MATERIAS_DIAP = [
    # --- 1er cuatrimestre ---
    ("DIAP06",     "Planificación Estratégica"),
    ("DIAP10-I",   "Gestión de Políticas Públicas I"),
    ("DIAP10-II",  "Gestión de Políticas Públicas II"),
    ("DIAP07",     "Gestión del Cambio"),

    # --- 2º cuatrimestre ---
    ("DIAP15-CEP", "Clínica de Evaluación de Proyectos"),
    ("DIAP12",     "Desarrollo Sustentable"),
    ("DIAP08-14-I","Gestión de la Big Data I"),
    ("DIAP08-14-II","Gestión de la Big Data II"),

    # --- 3er cuatrimestre ---
    ("DIAP13-I",   "Inteligencia Artificial I (Gestión de Proyectos)"),
    ("DIAP13-II",  "Inteligencia Artificial II"),
    ("DIAP15-EP",  "Evaluación de Proyectos"),
    ("DIAP08",     "Simplificación de Procesos"),

    # --- 4º cuatrimestre ---
    ("DIAP11-I",   "Innovación y Desarrollo I"),
    ("DIAP11-II",  "Innovación y Desarrollo II"),
    ("DIAP01",     "Economía Disruptiva"),
    ("DIAP02",     "Metodología de la Investigación"),

    # --- 5º cuatrimestre ---
    ("DIAP03",     "Análisis de Sistemas"),
    ("DIAP09",     "Gestión de la Calidad"),
    ("DIAP05",     "Modelos de Investigación Regional"),
    ("DIAP04",     "Seminario de Investigación"),
]

class Command(BaseCommand):
    help = "Crea/actualiza las materias del Doctorado en Innovación, Administración y Políticas Públicas dentro de un Programa."

    def add_arguments(self, parser):
        parser.add_argument(
            "--programa-codigo",
            help="Código del programa (ej. 'DIAP'). Si se omite, intenta encontrar por nombre.",
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

        # Buscar por nombre exacto y luego por icontains
        nombre_objetivo = "Doctorado en Innovación, Administración y Políticas Públicas"
        qs = Programa.objects.filter(nombre__iexact=nombre_objetivo)
        if not qs.exists():
            qs = Programa.objects.filter(nombre__icontains="Innovación, Administración y Políticas Públicas")
        if qs.count() == 1:
            return qs.first()
        if qs.count() > 1:
            raise CommandError(
                "Hay múltiples Programas cuyo nombre coincide con el DIAP. "
                "Usa --programa-codigo para especificar."
            )

        # Último intento: código 'DIAP'
        try:
            return Programa.objects.get(codigo__iexact="DIAP")
        except Programa.DoesNotExist:
            raise CommandError(
                "No encontré el Programa DIAP. "
                "Indica uno con --programa-codigo=DIAP (o el que corresponda)."
            )

    def handle(self, *args, **opts):
        programa = self._resolver_programa(opts.get("programa_codigo"))
        self.stdout.write(self.style.HTTP_INFO(f"Programa objetivo: {programa.codigo} — {programa.nombre}"))

        created, updated = 0, 0
        for codigo, nombre in MATERIAS_DIAP:
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
#python manage.py cargar_diap_materias --programa-codigo=DIAP
