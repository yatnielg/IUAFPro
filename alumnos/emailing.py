# alumnos/emailing.py
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.contrib.staticfiles import finders
from django.utils.html import strip_tags
from email.mime.image import MIMEImage
from typing import List, Optional
import os

def _attach_inline_logo(message, static_path: str = "iuaf/logo-email.png", cid: str = "logo_cid"):
    """
    Adjunta un logo inline (opcional). Asegúrate de tener /static/iuaf/logo-email.png
    y en el HTML usa: <img src="cid:logo_cid" ...>
    """
    try:
        path = finders.find(static_path)
        if not path:
            return
        with open(path, "rb") as f:
            img = MIMEImage(f.read())
            img.add_header("Content-ID", f"<{cid}>")
            img.add_header("Content-Disposition", "inline", filename=os.path.basename(path))
            message.attach(img)
    except Exception:
        pass

def _find_static(path_rel: str) -> Optional[str]:
    """Devuelve ruta absoluta del archivo estático o None si no existe."""
    try:
        return finders.find(path_rel)
    except Exception:
        return None

def send_static_welcome_pack(
    *,
    to_email: str,
    alumno_nombre: str = "",
    subject: str = "¡Bienvenido(a) a IUAF! 📚✨",
    intro: str = "",
    attachments_static: Optional[List[str]] = None,
    from_email: Optional[str] = None,
    portal_url: Optional[str] = None,
) -> dict:
    """
    Envía un correo de bienvenida con adjuntos ubicados en /static/.
    - attachments_static: rutas relativas dentro de /static/ (ej: "iuaf/bienvenida/Calendario.pdf")
    - portal_url: si quieres un botón "Ir al portal"
    """
    attachments_static = attachments_static or []

    ctx = {
        "alumno_nombre": alumno_nombre.strip(),
        "intro": intro.strip() or "Adjuntamos tu paquete de bienvenida con documentos importantes.",
        "portal_url": portal_url or "",
        "subject": subject,
    }

    html = render_to_string("emails/bienvenida_pack.html", ctx)
    text = render_to_string("emails/bienvenida_pack.txt", ctx) if False else strip_tags(html)

    msg = EmailMultiAlternatives(
        subject=subject,
        body=text,
        from_email=from_email,   # usa DEFAULT_FROM_EMAIL si es None
        to=[to_email],
    )
    msg.attach_alternative(html, "text/html")

    # Logo inline (opcional)
    _attach_inline_logo(msg, "iuaf/logo-email.png", "logo_cid")

    # Adjuntos desde /static/
    missing = []
    for rel in attachments_static:
        abs_path = _find_static(rel)
        if not abs_path:
            missing.append(rel)
            continue
        try:
            with open(abs_path, "rb") as f:
                data = f.read()
            filename = os.path.basename(rel)
            msg.attach(filename, data)  # Django deduce mime por extensión (ok para PDF/IMG)
        except Exception:
            missing.append(rel)

    try:
        msg.send(fail_silently=False)
        ok = True
        err = None
    except Exception as e:
        ok = False
        err = str(e)

    return {
        "ok": ok,
        "error": err,
        "missing": missing,
        "sent_to": to_email,
    }
