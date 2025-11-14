# academico/management/commands/crear_listados_materias.py
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from academico.models import Materia, ListadoMaterias, ListadoMateriaItem
from alumnos.models import Programa


class Command(BaseCommand):
    help = (
        "Crea un ListadoMaterias por programa y le agrega todas las Materias "
        "de ese programa como ListadoMateriaItem."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--programa-codigo",
            help="Código del programa (ej. 'DIAP'). "
                 "Si se omite, se procesan todos los programas que tienen materias.",
        )
        parser.add_argument(
            "--nombre",
            help=(
                "Nombre base del listado. "
                "Si se omite, se usará 'Listado automático <PROG> <YYYY-MM-DD>'."
            ),
        )
        parser.add_argument(
            "--descripcion",
            help="Descripción opcional del listado.",
            default="Listado creado automáticamente desde comando de gestión.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Muestra lo que haría sin escribir en la base de datos.",
        )

    def _get_programas(self, programa_codigo: str | None):
        """
        Si se indica un código de programa, devuelve sólo ese.
        Si no, devuelve todos los programas que tienen al menos una Materia.
        """
        if programa_codigo:
            try:
                programa = Programa.objects.get(codigo__iexact=programa_codigo.strip())
            except Programa.DoesNotExist:
                raise CommandError(f"No existe Programa con código '{programa_codigo}'.")
            return [programa]

        # Todos los programas que tengan al menos una materia
        programas = (
            Programa.objects.filter(materias__isnull=False)
            .distinct()
            .order_by("codigo")
        )
        if not programas.exists():
            raise CommandError("No hay programas con materias registradas.")
        return list(programas)

    def handle(self, *args, **opts):
        programa_codigo = opts.get("programa_codigo")
        nombre_base = opts.get("nombre")
        descripcion = opts.get("descripcion")
        dry_run = opts.get("dry_run", False)

        programas = self._get_programas(programa_codigo)

        self.stdout.write(self.style.HTTP_INFO(
            f"Programas a procesar: {', '.join(p.codigo for p in programas)}"
        ))

        total_listados_creados = 0
        total_items_creados = 0

        hoy = timezone.now().date().strftime("%Y-%m-%d")

        for programa in programas:
            # Nombre del listado
            if nombre_base:
                nombre_listado = nombre_base
            else:
                nombre_listado = f"Listado automático {programa.codigo} {hoy}"

            if dry_run:
                self.stdout.write(
                    f"[dry-run] Programa {programa.codigo}: "
                    f"crearía/actualizaría ListadoMaterias '{nombre_listado}'"
                )
            else:
                listado, created = ListadoMaterias.objects.get_or_create(
                    programa=programa,
                    nombre=nombre_listado,
                    defaults={"descripcion": descripcion or ""},
                )
                if not created and descripcion:
                    # Si ya existía, actualizamos descripción si viene algo
                    listado.descripcion = descripcion
                    listado.save(update_fields=["descripcion"])

                if created:
                    total_listados_creados += 1
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"✓ Creado ListadoMaterias para {programa.codigo}: '{nombre_listado}'"
                        )
                    )
                else:
                    self.stdout.write(
                        self.style.WARNING(
                            f"• Usando ListadoMaterias existente para {programa.codigo}: '{nombre_listado}'"
                        )
                    )

            # Materias del programa
            materias_qs = Materia.objects.filter(programa=programa).order_by("codigo")
            if not materias_qs.exists():
                self.stdout.write(
                    self.style.WARNING(
                        f"Programa {programa.codigo} no tiene materias; se omiten items."
                    )
                )
                continue

            items_creados_prog = 0

            for materia in materias_qs:
                if dry_run:
                    self.stdout.write(
                        f"[dry-run]   - Vincularía materia {materia.codigo} — {materia.nombre}"
                        f" al listado '{nombre_listado}'"
                    )
                    continue

                # Recuperar el listado (fuera del dry-run ya lo tenemos)
                listado = ListadoMaterias.objects.get(programa=programa, nombre=nombre_listado)

                item, created_item = ListadoMateriaItem.objects.get_or_create(
                    listado=listado,
                    materia=materia,
                    defaults={
                        "fecha_inicio": None,
                        "fecha_fin": None,
                    },
                )
                if created_item:
                    items_creados_prog += 1
                    total_items_creados += 1
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"   ✓ Agregada materia {materia.codigo} — {materia.nombre}"
                        )
                    )
                else:
                    self.stdout.write(
                        self.style.HTTP_NOT_MODIFIED(
                            f"   • Ya existía materia {materia.codigo} — {materia.nombre} en el listado"
                        )
                    )

            if not dry_run:
                self.stdout.write(
                    self.style.MIGRATE_HEADING(
                        f"Programa {programa.codigo}: {items_creados_prog} items nuevos."
                    )
                )

        if not dry_run:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Resumen final: {total_listados_creados} listados creados, "
                    f"{total_items_creados} items de materias nuevos."
                )
            )
        else:
            self.stdout.write(self.style.HTTP_INFO("Dry-run finalizado. No se realizaron cambios."))
#python manage.py crear_listados_materias --programa-codigo=DIAP