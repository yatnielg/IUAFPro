# alumnos/management/commands/init_roles.py
from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group
from alumnos.permisos import (
    GRUPO_PAGOS, GRUPO_DOCUMENTOS,
    GRUPO_EDITAR_ESTATUS_ACADEMICO, GRUPO_EDITAR_ESTATUS_ADMIN
)

class Command(BaseCommand):
    help = "Crea grupos base (pagos, documentos, editar_estatus_*) si no existen."

    def handle(self, *args, **opts):
        created = []
        for name in [GRUPO_PAGOS, GRUPO_DOCUMENTOS, GRUPO_EDITAR_ESTATUS_ACADEMICO, GRUPO_EDITAR_ESTATUS_ADMIN]:
            g, ok = Group.objects.get_or_create(name=name)
            if ok:
                created.append(name)
        if created:
            self.stdout.write(self.style.SUCCESS(f"Grupos creados: {', '.join(created)}"))
        else:
            self.stdout.write("Todos los grupos ya existían.")
