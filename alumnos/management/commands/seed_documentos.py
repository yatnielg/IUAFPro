# alumnos/management/commands/seed_documentos.py
from django.core.management.base import BaseCommand
from django.db import transaction

from alumnos.models import Programa, DocumentoTipo, ProgramaDocumentoRequisito

DEFAULT_TIPOS = [
    # slug, nombre, multiple
    ("acta-nacimiento",         "Acta de nacimiento",                     False),
    ("curp",                    "CURP",                                    False),
    ("certificado-estudios",    "Certificado de estudios",                 False),
    ("titulo-grado",            "Título o grado de estudios",              False),
    ("solicitud-registro",      "Solicitud de registro",                   False),
    ("validacion-autenticidad", "Documento de validación de autenticidad", False),
    ("carta-compromiso",        "Carta compromiso",                         False),
    ("carta-interes",           "Carta de interés académico",              False),
    ("identificacion-oficial",  "Identificación oficial",                  False),
    # Si quieres dejar un comodín opcional por programa, puedes activarlo:
    # ("otro-documento",          "Otro documento",                           True),
]

DEFAULT_REQUISITOS = {
    # slug -> (obligatorio, minimo, maximo)
    "acta-nacimiento":         (True,  1, 1),
    "curp":                    (True,  1, 1),
    "certificado-estudios":    (True,  1, 1),
    "titulo-grado":            (False, 1, 1),  # suele ser obligatorio para posgrado; puedes volverlo True por CLI
    "solicitud-registro":      (True,  1, 1),
    "validacion-autenticidad": (False, 1, 1),
    "carta-compromiso":        (True,  1, 1),
    "carta-interes":           (False, 1, 1),
    "identificacion-oficial":  (True,  1, 1),
    # "otro-documento":           (False, 0, 5),
}


class Command(BaseCommand):
    help = (
        "Crea por defecto los tipos de documentos y los asigna como requisitos a Programas.\n"
        "Idempotente: puedes ejecutarlo varias veces."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--programa-codigo",
            help="Limita la asignación de requisitos a un solo Programa (p.ej. MD, LD, DD).",
        )
        parser.add_argument(
            "--hacer-obligatorios",
            nargs="*",
            default=[],
            help="Lista de slugs a forzar como obligatorios (p.ej. 'titulo-grado carta-interes').",
        )
        parser.add_argument(
            "--hacer-opcionales",
            nargs="*",
            default=[],
            help="Lista de slugs a forzar como opcionales.",
        )
        parser.add_argument(
            "--activar-tipo",
            nargs="*",
            default=[],
            help="Slugs de DocumentoTipo a marcar como activos (si estaban inactivos).",
        )
        parser.add_argument(
            "--desactivar-tipo",
            nargs="*",
            default=[],
            help="Slugs de DocumentoTipo a marcar como inactivos.",
        )
        parser.add_argument(
            "--solo-tipos",
            action="store_true",
            help="Solo crea/actualiza DocumentoTipo; no asigna requisitos a Programas.",
        )
        parser.add_argument(
            "--solo-requisitos",
            action="store_true",
            help="No crea tipos; solo (re)asigna requisitos a Programas.",
        )

    @transaction.atomic
    def handle(self, *args, **opts):
        programa_codigo = opts.get("programa_codigo")
        forzar_obl = set(opts.get("hacer_obligatorios") or [])
        forzar_opc = set(opts.get("hacer_opcionales") or [])
        activar = set(opts.get("activar_tipo") or [])
        desactivar = set(opts.get("desactivar_tipo") or [])
        solo_tipos = bool(opts.get("solo_tipos"))
        solo_reqs = bool(opts.get("solo_requisitos"))

        if solo_tipos and solo_reqs:
            self.stderr.write(self.style.ERROR("No puedes usar --solo-tipos y --solo-requisitos a la vez."))
            return

        # 1) Crear/actualizar DocumentoTipo
        if not solo_reqs:
            self.stdout.write(self.style.NOTICE("Creando/actualizando DocumentoTipo..."))
            for slug, nombre, multiple in DEFAULT_TIPOS:
                obj, created = DocumentoTipo.objects.get_or_create(
                    slug=slug,
                    defaults={"nombre": nombre, "multiple": multiple, "activo": True},
                )
                changed = False
                if not created:
                    if obj.nombre != nombre:
                        obj.nombre = nombre
                        changed = True
                    if obj.multiple != multiple:
                        obj.multiple = multiple
                        changed = True
                # Activar / desactivar por CLI
                if slug in activar and not obj.activo:
                    obj.activo = True
                    changed = True
                if slug in desactivar and obj.activo:
                    obj.activo = False
                    changed = True

                if changed:
                    obj.save()
                    self.stdout.write(f"  - Actualizado: {slug}")
                elif created:
                    self.stdout.write(f"  + Creado: {slug}")
                else:
                    self.stdout.write(f"  = Sin cambios: {slug}")

        if solo_tipos:
            self.stdout.write(self.style.SUCCESS("Listo (solo tipos)."))
            return

        # 2) Asignar requisitos a Programas
        qs_prog = Programa.objects.all()
        if programa_codigo:
            qs_prog = qs_prog.filter(codigo=programa_codigo)

        if not qs_prog.exists():
            self.stderr.write(self.style.ERROR("No hay Programas que coincidan con el filtro."))
            return

        self.stdout.write(self.style.NOTICE(f"Asignando requisitos a {qs_prog.count()} Programa(s)..."))

        tipos_map = {t.slug: t for t in DocumentoTipo.objects.all()}

        for prog in qs_prog:
            self.stdout.write(self.style.HTTP_INFO(f"Programa: {prog.codigo} — {prog.nombre}"))

            for slug, cfg in DEFAULT_REQUISITOS.items():
                if slug not in tipos_map:
                    self.stderr.write(self.style.WARNING(f"  ! Tipo '{slug}' no existe. Saltando..."))
                    continue

                obligatorio, minimo, maximo = cfg

                # Overrides CLI
                if slug in forzar_obl:
                    obligatorio = True
                if slug in forzar_opc:
                    obligatorio = False

                req, created = ProgramaDocumentoRequisito.objects.get_or_create(
                    programa=prog,
                    tipo=tipos_map[slug],
                    defaults={
                        "obligatorio": obligatorio,
                        "minimo": minimo,
                        "maximo": maximo,
                        "activo": True,
                    },
                )

                changed = False
                if not created:
                    # si algo cambió, actualizamos para dejar consistente con defaults + overrides
                    if req.obligatorio != obligatorio:
                        req.obligatorio = obligatorio
                        changed = True
                    if req.minimo != minimo:
                        req.minimo = minimo
                        changed = True
                    if req.maximo != maximo:
                        req.maximo = maximo
                        changed = True
                    if not req.activo:
                        req.activo = True
                        changed = True
                    if changed:
                        req.save()

                if created:
                    self.stdout.write(f"  + Requisito creado: {slug} (oblig={obligatorio}, min={minimo}, max={maximo})")
                elif changed:
                    self.stdout.write(f"  ~ Requisito actualizado: {slug} (oblig={obligatorio}, min={minimo}, max={maximo})")
                else:
                    self.stdout.write(f"  = Requisito sin cambios: {slug}")

        self.stdout.write(self.style.SUCCESS("¡Listo! Tipos y requisitos sembrados/actualizados."))

#Sembrar todo (tipos + requisitos para todos los programas):        
#python manage.py seed_documentos

#Solo crear/actualizar tipos (sin tocar requisitos):
#python manage.py seed_documentos --solo-tipos


#Solo requisitos (si ya existen los tipos):
#python manage.py seed_documentos --solo-requisitos

#Limitar a un programa específico:
#python manage.py seed_documentos --programa-codigo MD

#Forzar algunos tipos como obligatorios u opcionales (override de defaults):
#python manage.py seed_documentos --hacer-obligatorios titulo-grado carta-interes
#python manage.py seed_documentos --hacer-opcionales validacion-autenticidad

#Activar / desactivar rápidamente tipos:
#python manage.py seed_documentos --activar-tipo titulo-grado --desactivar-tipo carta-interes


