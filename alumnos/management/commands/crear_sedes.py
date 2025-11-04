# alumnos/management/commands/crear_sedes.py
from django.core.management.base import BaseCommand
from alumnos.models import Sede  # ajusta si tu app no es "alumnos"

class Command(BaseCommand):
    help = "Crea sedes predefinidas sin país ni estado"

    SEDES = [
        "CANCÚN",
        "PUERTO M",
        "KANTUNILKÍN",
        "CIUDAD DEL C",
        "CHETUMAL",
        "TOLUCA",
        "PANAMÁ",
        "GUATEMALA",
        "CHIAPAS",
        "MONTERREY",
        "SALTILLO",
    ]

    def handle(self, *args, **options):
        creadas = 0
        for nombre in self.SEDES:
            obj, created = Sede.objects.get_or_create(nombre=nombre, defaults={"activo": True})
            if created:
                creadas += 1
                self.stdout.write(self.style.SUCCESS(f"+ Creada: {nombre}"))
            else:
                self.stdout.write(f"= Ya existía: {nombre}")
        self.stdout.write(self.style.WARNING(f"Sedes nuevas: {creadas}"))

#python manage.py crear_sedes