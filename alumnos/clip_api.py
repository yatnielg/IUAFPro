# alumnos/clip_api.py
import uuid, base64, re, unicodedata, hmac, hashlib
import requests
from typing import Optional, Tuple
from .utils import get_active_clip_credential

CLIP_BASE_URL = "https://api.payclip.com"
CLIP_ENDPOINT_CREATE   = "/v2/checkout"
CLIP_ENDPOINT_STATUS   = "/v2/checkout/{payment_req_id}"
CLIP_ENDPOINT_PAYMENT  = "/payments/{payment_id}"
DEFAULT_TIMEOUT = 20

def _sanitize_description(text: str, max_len: int = 60) -> str:
    if not text:
        return "Pago"
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = text.replace("—", "-").replace("–", "-")
    text = re.sub(r"[^A-Za-z0-9 .,-]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_len] or "Pago"

class ClipClient:
    def __init__(self, sandbox: Optional[bool] = None):
        cred = get_active_clip_credential(sandbox=sandbox)
        if not cred or not cred.public_key or not cred.secret_key:
            raise RuntimeError("No hay credenciales Clip activas/configuradas (api_key y secret).")
        self.api_key = cred.public_key.strip()
        self.secret  = cred.secret_key.strip()
        self.base_url = CLIP_BASE_URL

    def _basic_auth(self) -> str:
        token = f"{self.api_key}:{self.secret}".encode("utf-8")
        return "Basic " + base64.b64encode(token).decode("ascii")

    def _headers(self, idempotency_key: Optional[str] = None):
        h = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": self._basic_auth(),
            "x-api-key": self.api_key,            # <-- fuerza envío de x-api-key
            "User-Agent": "CampusIUAF/ClipClient",
        }
        if idempotency_key:
            h["Idempotency-Key"] = idempotency_key
        return h

    # ==== Helper para parsear seguro ====
    def _parse_response(self, resp: requests.Response) -> Tuple[dict, int]:
        code = getattr(resp, "status_code", 0) or 0
        body_text = ""
        try:
            body_text = resp.text or ""
        except Exception:
            body_text = ""
        try:
            # aunque diga application/json, si no es JSON caerá al except
            return resp.json(), code
        except Exception:
            # devolvemos info útil para depurar
            data = {
                "_raw_text": body_text[:2000],
                "_http_status": code,
                "_content_type": resp.headers.get("content-type", ""),
            }
            # pista típica de credenciales / auth
            if code in (401, 403):
                data["message"] = "Unauthorized/Forbidden (revisa api_key, secret y x-api-key)"
            return data, code

    # ==== API ====
    def create_payment_link(
        self,
        *,
        amount: float | str,
        description: str,
        order_id: str,
        success_url: str,
        cancel_url: str,
        metadata: dict | None = None,
        use_cents: bool = True,       # <-- por defecto en centavos
        description_max_len: int = 60,
    ) -> Tuple[dict, int]:

        url = self.base_url + CLIP_ENDPOINT_CREATE
        idem = str(uuid.uuid4())

        try:
            amt = float(amount)
        except Exception:
            raise ValueError("amount debe convertirse a número (float).")

        desc_sanitized = _sanitize_description(description, max_len=description_max_len)

        if use_cents:
            payload = {
                "amount": { "value": int(round(amt * 100)), "currency": "MXN" },
                "description": desc_sanitized,
                "reference": order_id,         # muchas cuentas usan 'reference'
                "success_url": success_url,
                "cancel_url": cancel_url,
                "metadata": metadata or {},
            }
        else:
            payload = {
                "amount": amt,
                "currency": "MXN",
                "description": desc_sanitized,
                "order_id": order_id,
                "success_url": success_url,
                "cancel_url": cancel_url,
                "metadata": metadata or {},
            }

        try:
            resp = requests.post(
                url, json=payload, headers=self._headers(idempotency_key=idem),
                timeout=DEFAULT_TIMEOUT
            )
        except requests.exceptions.RequestException as e:
            return {"error": "connection_error", "detail": str(e)}, 0

        data, code = self._parse_response(resp)
        # si API no manda message en error, añade uno básico
        if code >= 400 and "message" not in data:
            data["message"] = data.get("_raw_text") or "Error no especificado por la API"
        return data, code

    def retrieve_payment_link_status(self, payment_req_id: str) -> Tuple[dict, int]:
        url = self.base_url + CLIP_ENDPOINT_STATUS.format(payment_req_id=payment_req_id)
        try:
            resp = requests.get(url, headers=self._headers(), timeout=DEFAULT_TIMEOUT)
        except requests.exceptions.RequestException as e:
            return {"error": "connection_error", "detail": str(e)}, 0
        return self._parse_response(resp)

    def retrieve_payment(self, payment_id: str) -> Tuple[dict, int]:
        url = self.base_url + CLIP_ENDPOINT_PAYMENT.format(payment_id=payment_id)
        try:
            resp = requests.get(url, headers=self._headers(), timeout=DEFAULT_TIMEOUT)
        except requests.exceptions.RequestException as e:
            return {"error": "connection_error", "detail": str(e)}, 0
        return self._parse_response(resp)

def verify_webhook_signature(secret: str, body_bytes: bytes, signature_header: str) -> bool:
    if not signature_header:
        return True  # solo dev
    mac = hmac.new(secret.encode("utf-8"), body_bytes, hashlib.sha256).hexdigest()
    return hmac.compare_digest(mac, signature_header)
