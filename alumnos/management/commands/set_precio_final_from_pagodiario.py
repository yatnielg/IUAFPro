# alumnos/management/commands/set_precio_final_from_pagodiario.py
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q
from alumnos.models import Alumno  # ajusta el import a tu app real

class Command(BaseCommand):
    help = (
        "Asigna InformacionEscolar.precio_final usando el primer PagoDiario "
        "del alumno cuyo concepto diga 'COLEGIATURA'. Si no hay, se omite."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Muestra lo que haría sin guardar cambios."
        )
        parser.add_argument(
            "--only-empty",
            action="store_true",
            help="Solo actualiza si precio_final está vacío (NULL)."
        )
        parser.add_argument(
            "--contains",
            default="COLEGIATURA",
            help="Texto a buscar en el campo concepto (por defecto: COLEGIATURA)."
        )

    @transaction.atomic
    def handle(self, *args, **opts):
        dry = opts["dry_run"]
        only_empty = opts["only_empty"]
        needle = opts["contains"]

        total = 0
        updated = 0
        skipped_no_pago = 0
        skipped_only_empty = 0
        skipped_same_value = 0
        skipped_no_plan = 0

        # Itera por todos los alumnos que tengan plan (InformacionEscolar)
        qs = (
            Alumno.objects.select_related("informacionEscolar")
            .all()
            .iterator(chunk_size=500)
        )

        for alumno in qs:
            total += 1
            plan = alumno.informacionEscolar
            if not plan:
                skipped_no_plan += 1
                continue

            # Busca el primer PagoDiario del alumno cuyo concepto contenga el texto
            # Tomamos el más antiguo por fecha
            pago = (
                alumno.pagos_diario
                .filter(concepto__icontains=needle)
                .order_by("fecha", "id")
                .first()
            )
            if not pago:
                skipped_no_pago += 1
                continue

            monto = pago.monto or Decimal("0.00")

            # Si solo debemos actualizar cuando precio_final esté NULL
            if only_empty and plan.precio_final is not None:
                skipped_only_empty += 1
                continue

            # Si ya tiene ese mismo valor, omite
            if plan.precio_final is not None and Decimal(plan.precio_final) == monto:
                skipped_same_value += 1
                continue

            # Actualiza
            msg = f"Alumno {alumno.numero_estudiante}: precio_final {plan.precio_final} -> {monto} (PagoDiario id={pago.id}, fecha={pago.fecha})"
            if dry:
                self.stdout.write("[DRY-RUN] " + msg)
            else:
                plan.precio_final = monto
                plan.save(update_fields=["precio_final", "actualizado_en"])
                self.stdout.write(msg)
                updated += 1

        self.stdout.write("")
        self.stdout.write("==== Resumen ====")
        self.stdout.write(f"Alumnos procesados: {total}")
        self.stdout.write(f"Actualizados: {updated}")
        self.stdout.write(f"Sin plan (InformacionEscolar): {skipped_no_plan}")
        self.stdout.write(f"Sin pago con concepto que contenga '{needle}': {skipped_no_pago}")
        self.stdout.write(f"Omitidos por --only-empty y ya tener precio_final: {skipped_only_empty}")
        self.stdout.write(f"Omitidos por ya tener el mismo valor: {skipped_same_value}")

        if dry:
            self.stdout.write("\n(Ejecución en modo DRY-RUN, no se guardaron cambios.)")
