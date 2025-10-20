# alumnos/utils.py
from django.db import transaction
from .models import ContadorAlumno
from typing import Optional

def siguiente_numero_estudiante():
    """
    Devuelve el siguiente número de estudiante de forma transaccional
    y segura para concurrencia.
    """
    with transaction.atomic():
        contador, _ = (ContadorAlumno.objects
                       .select_for_update()
                       .get_or_create(llave="global"))
        contador.ultimo_numero = (contador.ultimo_numero or 0) + 1
        contador.save(update_fields=["ultimo_numero"])
        return contador.ultimo_numero

###############################################################
from .models import ClipCredential
from django.core.exceptions import ObjectDoesNotExist

def get_active_clip_credential(sandbox=None):
    """
    Retorna la credencial activa.
    Si sandbox es True/False lo filtra; si es None busca la activa por defecto.
    Lanza None si no existe.
    """
    qs = ClipCredential.objects.all()
    if sandbox is True:
        qs = qs.filter(is_sandbox=True)
    elif sandbox is False:
        qs = qs.filter(is_sandbox=False)

    try:
        # preferimos la que tenga active=True
        cred = qs.filter(active=True).first()
        if not cred:
            cred = qs.first()
        return cred
    except ObjectDoesNotExist:
        return None
###############################################################
# alumnos/utils_twilio.py
from .models import TwilioConfig

def get_active_twilio_config(environment: str | None = None) -> TwilioConfig | None:
    """
    Si environment es None, prioriza una activa de prod y si no hay, sandbox.
    Si lo pasas explícito ('prod'/'sandbox'), toma esa.
    """
    qs = TwilioConfig.objects.filter(active=True)
    if environment:
        cfg = qs.filter(environment=environment).first()
        return cfg
    # Prioridad: prod -> sandbox
    return qs.filter(environment="prod").first() or qs.filter(environment="sandbox").first()
##################
# alumnos/twilio_client.py
from twilio.rest import Client
from django.core.exceptions import ImproperlyConfigured
#from .utils_twilio import get_active_twilio_config

def _get_cfg(env: str | None = None):
    cfg = get_active_twilio_config(env)
    if not cfg:
        raise ImproperlyConfigured("No hay TwilioConfig activa.")
    missing = []
    if not cfg.account_sid: missing.append("account_sid")
    if not cfg.auth_token: missing.append("auth_token")
    if missing:
        raise ImproperlyConfigured(f"TwilioConfig incompleta: falta {', '.join(missing)}")
    return cfg

def get_twilio_client(env: str | None = None) -> Client:
    cfg = _get_cfg(env)
    return Client(cfg.account_sid, cfg.auth_token)

def send_sms(to_e164: str, body: str, env: str | None = None, status_callback: str | None = None):
    cfg = _get_cfg(env)
    client = get_twilio_client(env)
    params = {
        "to": to_e164,
        "body": body[:1600],
    }
    # Prioriza Messaging Service SID si lo configuraste
    if cfg.messaging_service_sid:
        params["messaging_service_sid"] = cfg.messaging_service_sid
    else:
        if not cfg.sms_from:
            raise ImproperlyConfigured("Falta sms_from o messaging_service_sid en TwilioConfig activa.")
        params["from_"] = cfg.sms_from
    if status_callback:
        params["status_callback"] = status_callback
    return client.messages.create(**params)

def send_whatsapp(to_e164: str, body: str, env: str | None = None, status_callback: str | None = None):
    cfg = _get_cfg(env)
    client = get_twilio_client(env)
    from_wa = cfg.whatsapp_from
    if not from_wa:
        raise ImproperlyConfigured("Falta whatsapp_from en TwilioConfig activa.")
    params = {
        "from_": from_wa,                 # ej 'whatsapp:+14155238886'
        "to": f"whatsapp:{to_e164}",      # ej 'whatsapp:+52XXXXXXXXXX'
        "body": body[:1600],
    }
    if status_callback:
        params["status_callback"] = status_callback
    return client.messages.create(**params)
###############################################################
# utils.py
from typing import Optional
from twilio.rest import Client
from django.core.exceptions import ImproperlyConfigured
from .models import TwilioConfig

# --- helpers internos ---
def _get_active_twilio_config(env: Optional[str] = None) -> TwilioConfig:
    qs = TwilioConfig.objects.filter(active=True)
    if env:
        qs = qs.filter(env=env)
    cfg = qs.first()
    if not cfg:
        raise ImproperlyConfigured("No hay TwilioConfig activa para el entorno solicitado.")
    if not cfg.account_sid or not cfg.auth_token:
        raise ImproperlyConfigured("TwilioConfig activa sin account_sid/auth_token.")
    return cfg

def _get_twilio_client(env: Optional[str] = None) -> tuple[Client, TwilioConfig]:
    cfg = _get_active_twilio_config(env)
    return Client(cfg.account_sid, cfg.auth_token), cfg

def _ensure_e164(number: str) -> str:
    """
    Asegura formato E.164 básico para SMS (ej. '+521234567890').
    Si viene sin '+', intenta anteponer '+'.
    """
    n = number.strip()
    if not n.startswith("+"):
        n = "+" + n
    return n

def _ensure_wa(number: str) -> str:
    """
    Asegura el prefijo 'whatsapp:' requerido por Twilio para WhatsApp.
    Acepta 'whatsapp:+52...' o '+52...' y lo normaliza.
    """
    n = number.strip()
    if n.startswith("whatsapp:"):
        return n
    n = _ensure_e164(n)
    return f"whatsapp:{n}"

# --- API pública que quieres: mensaje + teléfono ---
def send_simple_sms(text: str, to: str, *, env: Optional[str] = None,
                    status_callback: Optional[str] = None):
    """
    Envía un SMS usando la TwilioConfig activa (o la del env indicado).
    Prioriza Messaging Service SID si está configurado; si no, usa 'sms_from'.
    """
    client, cfg = _get_twilio_client(env)
    to_e164 = _ensure_e164(to)

    # Construye kwargs según lo que tengas configurado
    kwargs = {
        "to": to_e164,
        "body": text,
    }
    if status_callback:
        kwargs["status_callback"] = status_callback

    # Si tienes Messaging Service SID, úsalo
    if cfg.messaging_service_sid:
        kwargs["messaging_service_sid"] = cfg.messaging_service_sid
    else:
        if not cfg.sms_from:
            raise ImproperlyConfigured(
                "No hay messaging_service_sid ni sms_from configurado en la TwilioConfig activa."
            )
        kwargs["from_"] = cfg.sms_from

    return client.messages.create(**kwargs)

def send_simple_whatsapp(text: str, to: str, *, env: Optional[str] = None,
                         status_callback: Optional[str] = None):
    """
    Envía un WhatsApp usando la TwilioConfig activa (o la del env indicado).
    Requiere 'whatsapp_from' configurado (o un Messaging Service habilitado para WA).
    """
    client, cfg = _get_twilio_client(env)
    to_wa = _ensure_wa(to)

    kwargs = {
        "to": to_wa,
        "body": text,
    }
    if status_callback:
        kwargs["status_callback"] = status_callback

    # WhatsApp normalmente NO usa Messaging Service SID (a menos que lo tengas habilitado).
    # Si lo tienes habilitado para WA, podrías usarlo igual que en SMS, pero lo común es usar 'from_'.
    if cfg.messaging_service_sid:
        # Solo úsalo si tu Messaging Service está configurado para el canal WhatsApp.
        kwargs["messaging_service_sid"] = cfg.messaging_service_sid
    else:
        if not cfg.whatsapp_from:
            raise ImproperlyConfigured(
                "No hay whatsapp_from configurado en la TwilioConfig activa."
            )
        # Asegura prefijo "whatsapp:" en el remitente también
        from_wa = cfg.whatsapp_from
        if not from_wa.startswith("whatsapp:"):
            from_wa = _ensure_wa(from_wa.replace("whatsapp:", ""))
        kwargs["from_"] = from_wa

    return client.messages.create(**kwargs)
###############################################################