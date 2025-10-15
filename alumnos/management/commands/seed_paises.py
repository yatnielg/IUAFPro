# tu_app/management/commands/seed_paises.py
from django.core.management.base import BaseCommand
from alumnos.models import Pais

PAISES = [
    {
        "nombre": "México",
        "codigo_iso2": "MX",
        "codigo_iso3": "MEX",
        "requiere_estado": True,   # En MX normalmente sí se requiere estado
    },
    {
        "nombre": "Panamá",
        "codigo_iso2": "PA",
        "codigo_iso3": "PAN",
        "requiere_estado": False,   # Configúralo como prefieras
    },
    {
        "nombre": "Guatemala",
        "codigo_iso2": "GT",
        "codigo_iso3": "GTM",
        "requiere_estado": False,   # Configúralo como prefieras
    },
]

class Command(BaseCommand):
    help = "Crea países base (México, Panamá, Guatemala) si no existen."

    def handle(self, *args, **options):
        creados = 0
        for p in PAISES:
            obj, created = Pais.objects.get_or_create(
                nombre=p["nombre"],
                defaults={
                    "codigo_iso2": p["codigo_iso2"],
                    "codigo_iso3": p["codigo_iso3"],
                    "requiere_estado": p["requiere_estado"],
                },
            )
            if not created:
                # Si ya existe, actualizamos por si cambiaste algo
                obj.codigo_iso2 = p["codigo_iso2"]
                obj.codigo_iso3 = p["codigo_iso3"]
                obj.requiere_estado = p["requiere_estado"]
                obj.save()
            else:
                creados += 1

        self.stdout.write(self.style.SUCCESS(
            f"Países creados/actualizados. Nuevos creados: {creados}"
        ))
