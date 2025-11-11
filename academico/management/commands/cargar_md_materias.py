# academico/management/commands/cargar_md_materias.py
from django.core.management.base import BaseCommand, CommandError
from academico.models import Materia
from alumnos.models import Programa

"""
Notas:
- En el folleto varias materias comparten “base” de código (p. ej. MD602 I/II,
  o MD401 para distintos módulos). Para mantener la unicidad (programa, codigo),
  aquí agrego sufijos estandarizados: -I, -II, -MERC, -JO-CIV, -JO-FAM, -JO-MERC.
  Si tu control escolar usa otros códigos, solo ajusta los valores del arreglo
  MATERIAS_MD y vuelve a ejecutar el comando.
"""

MATERIAS_MD = [
    # ---------- PRIMER CUATRIMESTRE ----------
    ("MD501",        "Derecho de Amparo"),
    ("MD601",        "Derecho Administrativo"),
    ("MD602-I",      "Informática Jurídica I"),
    ("MD602-II",     "Informática Jurídica II"),

    # ---------- SEGUNDO CUATRIMESTRE ----------
    ("MD503-I",      "Recursos en el Procedimiento Escrito y Juicio Oral I"),
    ("MD503-II",     "Recursos en el Procedimiento Escrito y Juicio Oral II"),
    ("MD202",        "Teoría General del Derecho Constitucional"),
    ("MD501-PF-I",   "Práctica Forense en el Derecho Procesal Civil I"),

    # ---------- TERCER CUATRIMESTRE ----------
    ("MD501-PF-II",  "Práctica Forense en el Derecho Procesal Civil II"),
    ("MD402",        "Medios Alternos de Solución de Conflictos"),
    ("MD30",         "Derecho Civil"),
    ("MD303",        "Derecho Familiar"),

    # ---------- CUARTO CUATRIMESTRE ----------
    ("MD401-MERC",   "Derecho Mercantil"),
    ("MD401-JO-CIV", "Juicios Orales Civil"),
    ("MD401-JO-FAM", "Juicios Orales Familiar"),
    ("MD401-JO-MERC","Juicios Orales Mercantil"),

    # ---------- QUINTO CUATRIMESTRE ----------
    ("MD603",        "Seminario de Tesis"),
    ("MD201",        "Métodos y Técnicas de la Investigación Jurídica"),
    ("MD203",        "El Derecho Procesal Constitucional Funcional"),
    ("MD403",        "Tratados y Organismos Internacionales"),
]

class Command(BaseCommand):
    help = "Crea/actualiza las materias de la Maestría en Derecho dentro de un Programa."

    def add_arguments(self, parser):
        parser.add_argument(
            "--programa-codigo",
            help="Código del programa (ej. 'MD'). Si se omite, intenta encontrar por nombre.",
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

        # Buscar por nombre
        nombre_objetivo = "Maestría en Derecho"
        qs = Programa.objects.filter(nombre__iexact=nombre_objetivo)
        if not qs.exists():
            qs = Programa.objects.filter(nombre__icontains="Maestría en Derecho")
        if qs.count() == 1:
            return qs.first()
        if qs.count() > 1:
            raise CommandError(
                "Hay múltiples Programas cuyo nombre coincide con 'Maestría en Derecho'. "
                "Usa --programa-codigo para especificar."
            )

        # Último intento: código por defecto 'MD'
        try:
            return Programa.objects.get(codigo__iexact="MD")
        except Programa.DoesNotExist:
            raise CommandError(
                "No encontré el Programa de Maestría en Derecho. "
                "Indica uno con --programa-codigo=MD (o el que corresponda)."
            )

    def handle(self, *args, **opts):
        programa = self._resolver_programa(opts.get("programa_codigo"))
        self.stdout.write(self.style.HTTP_INFO(f"Programa objetivo: {programa.codigo} — {programa.nombre}"))

        created, updated = 0, 0
        for codigo, nombre in MATERIAS_MD:
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
#python manage.py cargar_md_materias --programa-codigo=MD
