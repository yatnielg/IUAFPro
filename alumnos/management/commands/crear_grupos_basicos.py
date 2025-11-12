# alumnos/management/commands/crear_grupos_basicos.py
from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType

GROUPS = [
    "Conciliadores Bancarios",
    "Supervisores Bancarios",
    "admisiones",
    "documentos",
    "editar_estatus_academico",
    "editar_estatus_administrativo",
    "pagos",    
]

BANCOS_GROUPS = {"Conciliadores Bancarios", "Supervisores Bancarios"}

class Command(BaseCommand):
    help = "Crea los grupos básicos de la plataforma si no existen. "\
           "Usa --with-perms para asignar permisos a los grupos bancarios."

    def add_arguments(self, parser):
        parser.add_argument(
            "--with-perms",
            action="store_true",
            help="Asigna permisos view/change sobre MovimientoBanco a los grupos bancarios."
        )

    def handle(self, *args, **options):
        created_count = 0
        for name in GROUPS:
            group, created = Group.objects.get_or_create(name=name)
            created_count += 1 if created else 0
            self.stdout.write(self.style.SUCCESS(f"✓ Grupo asegurado: {name} (creado={created})"))

        if options["with_perms"]:
            self._assign_bank_permissions()

        self.stdout.write(self.style.MIGRATE_HEADING(
            f"Listo. Grupos creados/normales: {created_count}/{len(GROUPS)}"
        ))

    def _assign_bank_permissions(self):
        """
        Asigna permisos view/change del modelo alumnos.MovimientoBanco a
        Conciliadores Bancarios y Supervisores Bancarios (si existen).
        """
        app_label = "alumnos"
        model = "movimientobanco"
        needed_codenames = {f"view_{model}", f"change_{model}"}

        try:
            ct = ContentType.objects.get(app_label=app_label, model=model)
        except ContentType.DoesNotExist:
            self.stdout.write(self.style.WARNING(
                f"No se encontró ContentType para {app_label}.{model}. "
                "Saltando asignación de permisos."
            ))
            return

        perms = Permission.objects.filter(content_type=ct, codename__in=needed_codenames)
        found = {p.codename for p in perms}
        missing = needed_codenames - found
        if missing:
            self.stdout.write(self.style.WARNING(
                f"Permisos faltantes {missing}. Asignaré sólo los encontrados: {sorted(found)}"
            ))

        for gname in BANCOS_GROUPS:
            try:
                g = Group.objects.get(name=gname)
            except Group.DoesNotExist:
                self.stdout.write(self.style.WARNING(
                    f"Grupo {gname} no existe (debería haberse creado)."
                ))
                continue
            g.permissions.add(*perms)
            self.stdout.write(self.style.SUCCESS(
                f"→ Asignados permisos {sorted(found)} a '{gname}'."
            ))
