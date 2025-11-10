from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from academico.models import ListadoMaterias, ListadoMateriaItem, ListadoAlumno, Calificacion

class Command(BaseCommand):
    help = "Crea entradas de Calificacion vacías para todos los alumnos inscritos en un listado y todas sus materias."

    def add_arguments(self, parser):
        parser.add_argument("--listado-id", type=int, required=True, help="ID del ListadoMaterias")

    @transaction.atomic
    def handle(self, *args, **opts):
        listado_id = opts["listado_id"]
        listado = ListadoMaterias.objects.filter(pk=listado_id).first()
        if not listado:
            raise CommandError(f"No existe ListadoMaterias id={listado_id}")

        items = list(ListadoMateriaItem.objects.filter(listado=listado).select_related("materia"))
        insc  = list(ListadoAlumno.objects.filter(listado=listado).select_related("alumno"))

        creadas = 0
        for it in items:
            for ins in insc:
                obj, created = Calificacion.objects.get_or_create(item=it, alumno=ins.alumno)
                if created:
                    creadas += 1

        self.stdout.write(self.style.SUCCESS(
            f"OK: Listado '{listado.nombre}' → {len(items)} materias, {len(insc)} alumnos, calificaciones nuevas: {creadas}."
        ))
