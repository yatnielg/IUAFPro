# alumnos/emails.py
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags

def enviar_bienvenida_alumno(alumno) -> bool:
    """
    Envía correo de bienvenida al alumno (HTML). Devuelve True/False.
    No lanza excepción hacia fuera.
    """
    return 0
    if not getattr(settings, "SEND_WELCOME_EMAILS", False):
        return False
    if not alumno.email:
        return False

    contexto = {
        "alumno": alumno,
        "programa": getattr(getattr(alumno, "informacionEscolar", None), "programa", None),
        "sede": getattr(getattr(alumno, "informacionEscolar", None), "sede", None),
    }

    subject = "¡Bienvenido(a) a IUAF!"
    html = render_to_string("emails/welcome_student.html", contexto)
    text = strip_tags(html)

    try:
        msg = EmailMultiAlternatives(
            subject=subject,
            body=text,
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None) or settings.EMAIL_HOST_USER,
            to=[alumno.email],
        )
        msg.attach_alternative(html, "text/html")
        msg.send(fail_silently=False)
        return True
    except Exception as e:
        # Log básico a consola; puedes integrar logging estructurado si prefieres
        print(f"[EMAIL] Error enviando bienvenida a {alumno.email}: {e}")
        return False
