# academico/management/commands/cargar_ld_materias.py
from django.core.management.base import BaseCommand, CommandError
from academico.models import Materia
from alumnos.models import Programa

"""
Carga/actualiza el catálogo de materias de la Licenciatura en Derecho (LD).
Los códigos 07LD–12LD vienen del folleto. Para los módulos sin código impreso
(p. ej. Introducción, Teoría Política, Evaluación, Práctica, Evaluación de
recuperación) definimos códigos claros para mantener la unicidad.
Si tu control escolar usa otros códigos oficiales, solo ajusta el arreglo
MATERIAS_LD y vuelve a ejecutar el comando.
"""

MATERIAS_LD = [
    # ---------- MÓDULOS DE INDUCCIÓN / GENERALES (del 1er bloque del folleto) ----------
    ("LD-INTRO-TP",  "Introducción al Derecho – Teoría Política"),
    ("LD-TEOPOL",    "Teoría Política"),
    ("LD-EVAL",      "Evaluación"),

    # ---------- MALLA MOSTRADA EN LOS BLOQUES 1° y 2° CUATRIMESTRE ----------
    ("07LD",         "Derecho Corporativo"),
    ("08LD",         "Teoría del Derecho Penal y del Delito"),
    ("09LD",         "Sociología Jurídica"),
    ("10LD",         "Derecho Notarial"),
    ("11LD",         "Derecho Mercantil"),
    ("12LD",         "Técnicas de la Investigación Jurídica"),

    # ---------- MÓDULOS OPERATIVOS (según el bloque del 2° cuatrimestre) ----------
    ("LD-PRACTICA",  "Práctica"),
    ("LD-EVAL-REC",  "Evaluación de Recuperación"),
]

class Command(BaseCommand):
    help = "Crea/actualiza las materias de la Licenciatura en Derecho (LD)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--programa-codigo",
            help="Código del programa (por defecto: 'LD').",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Simula la carga sin modificar la base de datos.",
        )

    def _resolver_programa(self, programa_codigo: str | None) -> Programa:
        codigo = (programa_codigo or "LD").strip()
        try:
            return Programa.objects.get(codigo__iexact=codigo)
        except Programa.DoesNotExist:
            # Intento por nombre
            nombre = "Licenciatura en Derecho"
            qs = Programa.objects.filter(nombre__iexact=nombre)
            if not qs.exists():
                qs = Programa.objects.filter(nombre__icontains="Licenciatura en Derecho")
            if qs.count() == 1:
                return qs.first()
            elif qs.count() > 1:
                raise CommandError(
                    "Hay múltiples Programas cuyo nombre coincide con 'Licenciatura en Derecho'. "
                    "Indica uno con --programa-codigo=LD."
                )
            raise CommandError(
                f"No encontré Programa con código '{codigo}' ni por nombre 'Licenciatura en Derecho'."
            )
        except Programa.MultipleObjectsReturned:
            raise CommandError(
                f"Existen múltiples Programas con código '{codigo}'. Especifica uno exacto."
            )

    def handle(self, *args, **opts):
        programa = self._resolver_programa(opts.get("programa_codigo"))
        self.stdout.write(self.style.HTTP_INFO(f"Programa objetivo: {programa.codigo} — {programa.nombre}"))

        created, updated = 0, 0
        for codigo, nombre in MATERIAS_LD:
            if opts["dry_run"]:
                self.stdout.write(f"[dry-run] ({programa.codigo}) {codigo:<12} {nombre}")
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
#python manage.py cargar_ld_materias --programa-codigo=LD
