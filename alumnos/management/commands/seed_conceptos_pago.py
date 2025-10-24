# -*- coding: utf-8 -*-
from django.core.management.base import BaseCommand
from django.db import transaction

from alumnos.models import ConceptoPago  # <-- cambia <tu_app> por el nombre real de tu app


CONCEPTOS = [
    # codigo, nombre, recurrente
    ("INSCRIPCION", "Inscripción", False),
    ("COLEGIATURA", "Colegiatura", True),
    ("APARTADO", "Apartado", False),
    ("INS/ COLE", "Inscripción/Colegiatura", False),
]


class Command(BaseCommand):
    help = "Crea/actualiza conceptos de pago base."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Muestra lo que haría sin escribir en BD.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        dry_run = options.get("dry_run", False)

        creados = 0
        actualizados = 0

        for codigo, nombre, recurrente in CONCEPTOS:
            codigo_norm = (codigo or "").strip()
            nombre_norm = (nombre or "").strip()

            if not codigo_norm or not nombre_norm:
                self.stderr.write(self.style.WARNING(
                    f"Saltando registro inválido: codigo='{codigo}', nombre='{nombre}'"
                ))
                continue

            defaults = {
                "nombre": nombre_norm,
                "recurrente": bool(recurrente),
            }

            if dry_run:
                self.stdout.write(
                    f"[DRY-RUN] update_or_create codigo='{codigo_norm}', defaults={defaults}"
                )
                continue

            obj, created = ConceptoPago.objects.update_or_create(
                codigo=codigo_norm,
                defaults=defaults,
            )
            if created:
                creados += 1
                self.stdout.write(self.style.SUCCESS(f"Creado: {obj}"))
            else:
                actualizados += 1
                self.stdout.write(self.style.NOTICE(f"Actualizado: {obj}"))

        if dry_run:
            self.stdout.write(self.style.WARNING("Dry-run completado."))
        else:
            self.stdout.write(self.style.SUCCESS(
                f"Listo. Creados: {creados}, Actualizados: {actualizados}"
            ))

# Ver qué haría sin tocar la BD
#python manage.py seed_conceptos_pago --dry-run
# Ejecutar realmente
#python manage.py seed_conceptos_pago