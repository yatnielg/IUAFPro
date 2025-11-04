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


# pip install pdfminer.six
from pdfminer.high_level import extract_text
import re

def datos_desde_constancia_pdf(path_pdf: str):
    texto = extract_text(path_pdf)
    # Los rótulos suelen ser así; ajusta si tu plantilla cambia
    get = lambda label: re.search(rf"{label}\s*:\s*(.+)", texto, re.IGNORECASE)
    def g(lbl):
        m = get(lbl)
        return m.group(1).strip() if m else ""

    return {
        "curp": g(r"CURP"),
        "nombre": g(r"Nombre\(s\)|Nombres"),
        "apellido_p": g(r"Primer apellido"),
        "apellido_m": g(r"Segundo apellido"),
        "sexo": g(r"Sexo"),
        "fecha_nacimiento": g(r"Fecha de nacimiento"),
        "nacionalidad": g(r"Nacionalidad"),
        "entidad_nacimiento": g(r"Entidad de nacimiento"),
    }



def datos_desde_gobmx_curp(curp_v2="GOHY840512HNENRT05"):
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException, NoSuchElementException
    from bs4 import BeautifulSoup
    import os, sys, shutil, time

    CURP = (curp_v2 or "").strip().upper()
    if not CURP:
        return {}

    opts = Options()
    # headless en servidor; en local puedes comentar esta línea para ver el navegador
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1280,1200")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    opts.add_argument(
        "user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )

    # ----------- INICIALIZACIÓN CROSS-PLATFORM -----------
    is_windows = sys.platform.startswith("win")
    try:
        if is_windows:
            # En Windows usamos webdriver_manager (cómodo para dev)
            from webdriver_manager.chrome import ChromeDriverManager
            # No pongas binary_location: Chrome se detecta solo si está instalado.
            service = Service(ChromeDriverManager().install())
        else:
            # En Linux/Docker usamos binarios del sistema (instálalos en la imagen)
            CHROME_BIN = os.getenv("CHROME_BIN", "/usr/bin/chromium")
            CHROMEDRIVER_BIN = os.getenv("CHROMEDRIVER_BIN", "/usr/bin/chromedriver")
            if not os.path.exists(CHROME_BIN):
                raise FileNotFoundError(f"No existe CHROME_BIN: {CHROME_BIN}")
            if not os.path.exists(CHROMEDRIVER_BIN):
                raise FileNotFoundError(f"No existe CHROMEDRIVER_BIN: {CHROMEDRIVER_BIN}")
            opts.binary_location = CHROME_BIN
            service = Service(CHROMEDRIVER_BIN)

        driver = webdriver.Chrome(service=service, options=opts)
    except Exception as e:
        # Fallback en Windows: intentar con Edge si existe
        if is_windows:
            try:
                from selenium.webdriver.edge.service import Service as EdgeService
                from selenium.webdriver.edge.options import Options as EdgeOptions
                from webdriver_manager.microsoft import EdgeChromiumDriverManager

                eopts = EdgeOptions()
                eopts.add_argument("--headless=new")
                eopts.add_argument("--no-sandbox")
                eopts.add_argument("--disable-dev-shm-usage")
                eopts.add_argument("--disable-gpu")
                eopts.add_argument("--window-size=1280,1200")
                service = EdgeService(EdgeChromiumDriverManager().install())
                driver = webdriver.Edge(service=service, options=eopts)
            except Exception:
                raise RuntimeError(
                    "No pude iniciar Chrome/Chromedriver en Windows. "
                    "Instala Google Chrome o usa Edge (tengo fallback), "
                    "o bien instala manualmente el driver. Error original: %r" % e
                )

    wait = WebDriverWait(driver, 25)

    try:
        driver.get("https://www.gob.mx/curp/")

        # 1) Overlay/captcha
        try:
            wait.until(EC.invisibility_of_element_located((By.ID, "sec-overlay")))
        except TimeoutException:
            raise RuntimeError("Overlay/captcha activo en gob.mx (no automatizable).")

        # 2) Input CURP
        possible_selectors = [
            (By.ID, "curpInput"),
            (By.CSS_SELECTOR, "input#curpInput"),
            (By.CSS_SELECTOR, "input[name='curp']"),
            (By.CSS_SELECTOR, "input[formcontrolname='curp']"),
            (By.CSS_SELECTOR, "input[type='text']"),
        ]
        curp_input = None
        for how, sel in possible_selectors:
            try:
                curp_input = wait.until(EC.element_to_be_clickable((how, sel)))
                break
            except TimeoutException:
                continue
        if not curp_input:
            raise NoSuchElementException("No se encontró el campo CURP (DOM cambió o captcha).")

        curp_input.clear()
        curp_input.send_keys(CURP)

        # 3) Click en Buscar
        clicked = False
        for how, sel in [
            (By.ID, "btnBuscar"),
            (By.CSS_SELECTOR, "button#btnBuscar"),
            (By.XPATH, "//button[contains(., 'Buscar')]"),
            (By.CSS_SELECTOR, "button[type='submit']"),
        ]:
            try:
                btn = driver.find_element(how, sel)
                btn.click()
                clicked = True
                break
            except Exception:
                pass
        if not clicked:
            curp_input.send_keys("\n")

        # 4) Esperar resultados
        try:
            wait.until(EC.presence_of_element_located(
                (By.XPATH, "//*[contains(., 'Datos del solicitante')]")
            ))
        except TimeoutException:
            raise RuntimeError("No aparecieron resultados; posible bloqueo/cambio de página.")

        time.sleep(1)

        # 5) Parse
        soup = BeautifulSoup(driver.page_source, "lxml")
        datos = {}
        h4 = soup.find("h4", string=lambda s: s and "Datos del solicitante" in s)
        if h4:
            panel_div = h4.find_parent("div", class_="panel")
            if panel_div:
                for row in panel_div.select("table tr"):
                    tds = row.find_all("td")
                    if len(tds) == 2:
                        etiqueta = tds[0].get_text(strip=True).rstrip(":")
                        valor = tds[1].get_text(strip=True)
                        datos[etiqueta] = valor

        if not datos:
            try:
                panel_elem = driver.find_element(
                    By.XPATH, "//h4[contains(., 'Datos del solicitante')]/ancestor::div[contains(@class,'panel')]"
                )
                for r in panel_elem.find_elements(By.CSS_SELECTOR, "table tr"):
                    tds = r.find_elements(By.TAG_NAME, "td")
                    if len(tds) == 2:
                        etiqueta = tds[0].text.strip().rstrip(":")
                        valor = tds[1].text.strip()
                        datos[etiqueta] = valor
            except Exception:
                pass

        salida = {
            "CURP": datos.get("CURP") or datos.get("Curp"),
            "Nombre": datos.get("Nombre(s)"),
            "PrimerApellido": datos.get("Primer apellido"),
            "SegundoApellido": datos.get("Segundo apellido"),
            "Sexo": datos.get("Sexo"),
            "FechaNacimiento": datos.get("Fecha de nacimiento"),
            "Nacionalidad": datos.get("Nacionalidad"),
            "EntidadNacimiento": datos.get("Entidad de nacimiento"),
        }
        return {k: v for k, v in salida.items() if v}
    finally:
        try:
            driver.quit()
        except Exception:
            pass



#########################################
# alumnos/utils_pdf.py
from io import BytesIO
from pypdf import PdfReader, PdfWriter
from PIL import Image
import os

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".webp"}

def _image_to_pdf_bytes(django_file) -> BytesIO:
    """
    Convierte una imagen subida (Django File) a PDF (1 página) y
    devuelve un buffer listo para leer con PdfReader.
    """
    django_file.open("rb")
    img = Image.open(django_file)
    if img.mode != "RGB":
        img = img.convert("RGB")
    out = BytesIO()
    img.save(out, format="PDF")
    out.seek(0)
    return out

def documentos_a_pdf(documentos, titulo="Documentos del alumno") -> bytes:
    """
    Recibe una instancia de DocumentosAlumno y retorna bytes de un PDF unificado.
    - Une PDFs tal cual
    - Convierte imágenes a PDF y las añade
    - Ignora campos vacíos
    """
    writer = PdfWriter()

    # Orden opcional de documentos (ajústalo como prefieras)
    campos = [
        "acta_nacimiento",
        "curp",
        "certificado_estudios",
        "titulo_grado",
        "solicitud_registro",
        "validacion_autenticidad",
        "carta_compromiso",
        "carta_interes",
        "identificacion_oficial",
        "otro_documento",
    ]

    for nombre in campos:
        f = getattr(documentos, nombre, None)
        if not f:
            continue

        _, ext = os.path.splitext(f.name or "")
        ext = ext.lower()

        try:
            if ext == ".pdf":
                f.open("rb")
                reader = PdfReader(f)
                for page in reader.pages:
                    writer.add_page(page)
            elif ext in IMAGE_EXTS:
                # convierte imagen a PDF y agrega su(s) página(s)
                img_pdf = _image_to_pdf_bytes(f)
                reader = PdfReader(img_pdf)
                for page in reader.pages:
                    writer.add_page(page)
            else:
                # Extensión no soportada: lo puedes loggear o añadir una “hoja separadora”
                # con reportlab si quieres. Por ahora lo ignoramos.
                continue
        finally:
            try:
                f.close()
            except Exception:
                pass

    # Metadatos
    writer.add_metadata({
        "/Title": titulo,
        "/Author": "Sistema de alumnos",
    })

    out = BytesIO()
    if len(writer.pages) == 0:
        # Si no hay páginas, generamos un PDF vacío para evitar respuesta corrupta
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import A4
        buf = BytesIO()
        c = canvas.Canvas(buf, pagesize=A4)
        c.setFont("Helvetica", 12)
        c.drawString(72, 800, "No hay documentos para mostrar.")
        c.showPage()
        c.save()
        buf.seek(0)
        reader = PdfReader(buf)
        for page in reader.pages:
            writer.add_page(page)

    writer.write(out)
    out.seek(0)
    return out.read()
##########################################################################################
from reportlab.lib.utils import ImageReader
def draw_fullwidth_image_bottom(c, page_width, left_margin, right_margin, bottom_margin, image_path):
    """
    Dibuja una imagen a todo lo ancho (respetando proporción) en la parte inferior de la página.
    - c: canvas
    - page_width: ancho de la página (W)
    - left_margin / right_margin: márgenes laterales
    - bottom_margin: separación desde el borde inferior
    - image_path: ruta absoluta del archivo de imagen
    """
    if not os.path.exists(image_path):
        return  # silencioso si no existe

    img = ImageReader(image_path)
    iw, ih = img.getSize()

    usable_w = page_width - left_margin - right_margin
    scale = usable_w / float(iw)
    scaled_h = ih * scale

    x = left_margin
    y = bottom_margin  # pega “bien abajo”

    # mask='auto' hace transparente el fondo si la imagen tiene alpha
    c.drawImage(img, x, y, width=usable_w, height=scaled_h, preserveAspectRatio=True, mask='auto')
