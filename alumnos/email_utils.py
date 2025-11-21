# alumnos/email_utils.py
import os
import mimetypes
import time
import random

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection
from django.contrib.staticfiles import finders
from django.template.loader import render_to_string
from django.utils import timezone

from .models import Alumno


def collect_attachments(rel_dir: str):
    """
    Busca archivos en una carpeta dentro de /static y devuelve
    [(abs_path, filename, mimetype), ...]
    Ej: rel_dir = 'iuaf/comunicados'
    """
    items = []

    for finder in finders.get_finders():
        if hasattr(finder, "locations"):
            for prefix, root in getattr(finder, "locations", []):
                sub = os.path.join(prefix, rel_dir) if prefix else rel_dir
                base = os.path.join(root, sub)
                if os.path.isdir(base):
                    for name in os.listdir(base):
                        path = os.path.join(base, name)
                        if os.path.isfile(path):
                            mime, _ = mimetypes.guess_type(path)
                            items.append((path, name, mime or "application/octet-stream"))

    unique = []
    seen = set()
    for abs_path, fname, mime in items:
        if abs_path not in seen:
            unique.append((abs_path, fname, mime))
            seen.add(abs_path)
    return unique


def enviar_correo_personalizado_a_alumnos(
    numeros_estudiante,
    subject: str,
    body_template: str,
    rel_dir_adjuntos: str | None = None,
    from_email: str | None = None,
    extra_attachments: list[tuple[str, bytes, str]] | None = None,
):
    """
    Envía un correo personalizado (por nombre) a una lista de alumnos,
    con versión texto plano + versión HTML con diseño.

    Variables en body_template:
      {nombre}, {apellido_p}, {apellido_m}, {numero}, {programa}
    """

    alumnos = list(
        Alumno.objects.filter(pk__in=numeros_estudiante)
        .select_related("informacionEscolar", "informacionEscolar__programa")
    )

    # Conexión SMTP
    if from_email is None:
        from_email = getattr(
            settings,
            "WELCOME_FROM_EMAIL",
            f"CampusIUAF <{settings.ADM_EMAIL_USER}>",
        )
        connection = get_connection(
            backend="django.core.mail.backends.smtp.EmailBackend",
            host=settings.EMAIL_HOST,
            port=settings.EMAIL_PORT,
            username=settings.ADM_EMAIL_USER,
            password=settings.ADM_EMAIL_PASSWORD,
            use_tls=settings.EMAIL_USE_TLS,
        )
    else:
        connection = get_connection()

    # Adjuntos estáticos
    attachments = []
    if rel_dir_adjuntos:
        attachments = collect_attachments(rel_dir_adjuntos)

    extra_attachments = extra_attachments or []

    # Config genérica para la imagen de encabezado y CTA
    header_url = getattr(
        settings,
        "MASIVO_HEADER_URL",
        # 👇 Cambia esto por la URL real donde tengas tu banner subido
        "https://tu-dominio.com/static/iuaf/doctorado-header.png",
    )
    cta_url = getattr(
        settings,
        "MASIVO_DOCTORADO_CTA_URL",
        "https://tu-dominio.com/doctorados",
    )

    enviados = []
    sin_correo = []
    errores = []

    for alumno in alumnos:
        to_email = (alumno.email or "").strip()
        if not to_email:
            sin_correo.append(alumno.pk)
            continue

        info = getattr(alumno, "informacionEscolar", None)
        programa = ""
        if info and getattr(info, "programa", None):
            programa = (
                getattr(info.programa, "nombre", "") or
                getattr(info.programa, "codigo", "")
            )

        # ===== 1) Cuerpo TEXTO PLANO (lo que escribes en el textarea) =====
        body_plain = body_template.format(
            nombre=alumno.nombre or "",
            apellido_p=alumno.apellido_p or "",
            apellido_m=alumno.apellido_m or "",
            numero=alumno.numero_estudiante,
            programa=programa,
        )

        # ===== 2) Convertir a HTML simple (respetando saltos de línea) =====
        # Línea por línea -> <br>, bloques separados por doble salto
        # (para no complicar, usamos simple <br>)
        body_html_inner = "<br>".join(
            line.replace("  ", "&nbsp;&nbsp;")
            for line in body_plain.splitlines()
        )

        # ===== 3) Renderizar el template bonito =====
        html_content = render_to_string(
            "emails/masivo_doctorado.html",
            {
                "alumno": alumno,
                "body_html": body_html_inner,
                "header_url": header_url,
                "cta_url": cta_url,
                "hoy": timezone.localdate(),
            },
        )

        try:
            msg = EmailMultiAlternatives(
                subject=subject,
                body=body_plain,          # texto plano
                from_email=from_email,
                to=[to_email],
                connection=connection,
            )

            # Versión HTML
            msg.attach_alternative(html_content, "text/html")

            # Adjuntos estáticos
            for abs_path, fname, mime in attachments:
                with open(abs_path, "rb") as f:
                    msg.attach(fname, f.read(), mime)

            # Adjuntos subidos desde el formulario
            for fname, content, mime in extra_attachments:
                msg.attach(fname, content, mime or "application/octet-stream")

            msg.send()
            enviados.append(alumno.pk)

            time.sleep(random.uniform(1.5, 1.9))

        except Exception as e:
            errores.append((alumno.pk, str(e)))

    return {
        "enviados": enviados,
        "sin_correo": sin_correo,
        "errores": errores,
        "total_intentados": len(alumnos),
    }
