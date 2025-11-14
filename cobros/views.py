import json
import stripe

from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.utils import timezone
from django.shortcuts import render

from .models import BillingInvite, PaymentRecord, WebhookEvent
from .services import create_checkout_for_invite

@csrf_exempt  # El link es público (token largo + expiración); puedes añadir rate limiting a nivel Nginx
def pagar_con_token(request, token):
    inv = get_object_or_404(BillingInvite, token=token)
    if not inv.is_valid():
        return HttpResponseBadRequest("Enlace inválido o expirado.")
    # Crea checkout y redirige
    url, pr = create_checkout_for_invite(inv, request=request)
    # marca uso tentativo (si quieres solo al completar, muévelo al webhook)
    inv.uses += 1
    inv.save(update_fields=["uses"])
    return HttpResponseRedirect(url)

@csrf_exempt
def stripe_webhook(request):
    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE", "")
    endpoint_secret = settings.STRIPE_WEBHOOK_SECRET
    try:
        event = stripe.Webhook.construct_event(payload=payload, sig_header=sig_header, secret=endpoint_secret)
    except stripe.error.SignatureVerificationError:
        return HttpResponse(status=400)
    except ValueError:
        return HttpResponse(status=400)

    # Guarda evento
    evt = WebhookEvent.objects.create(
        provider_event_id=event["id"],
        event_type=event["type"],
        payload=event
    )

    try:
        _handle_stripe_event(event)
        evt.processed_at = timezone.now()
        evt.save(update_fields=["processed_at"])
    except Exception as exc:
        evt.error = str(exc)
        evt.save(update_fields=["error"])
        # puedes registrar logs
    return HttpResponse(status=200)




def _get_pr_from_session_or_metadata(data):
    """
    Intenta resolver el PaymentRecord asociado a un evento de Stripe usando:
    1) metadata.pr_id (determinístico)
    2) checkout_session_id (fallback)
    """
    from .models import PaymentRecord  # import local para facilitar copy-paste

    # 1) por metadata.pr_id
    pr_id = (data.get("metadata") or {}).get("pr_id")
    if pr_id:
        try:
            return PaymentRecord.objects.get(pk=pr_id)
        except PaymentRecord.DoesNotExist:
            pass

    # 2) por checkout_session_id (id de la Checkout Session)
    sid = data.get("id", "")
    if sid:
        pr = PaymentRecord.objects.filter(checkout_session_id=sid).first()
        if pr:
            return pr

    return None


######################
# --- Helper para crear PagoDiario de forma idempotente ---
from django.utils import timezone

def _ensure_pago_diario_for_pr(pr, *, pi_id=None, cs_id=None, amount=None):
    """
    Crea un PagoDiario a partir de un PaymentRecord ya 'paid'.
    Idempotente: usa no_auto=payment_intent_id (o checkout_session_id) para no duplicar.
    """
    # Import local: ajusta si PagoDiario está en otra app
    try:
        from alumnos.models import PagoDiario  # <-- cambia este import si tu modelo está en otra app
    except Exception:
        # Si tu modelo PagoDiario no está en alumnos.models, ajusta el import arriba
        raise

    if not pr or pr.status != "paid":
        return None

    # Si ya existe un PagoDiario asociado al PI/CS, no duplica
    key = (pi_id or "") or (cs_id or "")
    if not key:
        # Sin IDs de Stripe es mejor no crear para evitar duplicados
        return None

    existing = PagoDiario.objects.filter(no_auto=key).first()
    if existing:
        return existing

    alumno = pr.alumno
    # Campos opcionales tomados de Alumno si existen
    nombre = None
    numero_alumno = None
    curp = None
    sede = None
    grado = None
    programa = None

    if alumno:
        # Ajusta según tus campos reales en Alumno
        nombre = " ".join(filter(None, [
            getattr(alumno, "nombre", None),
            getattr(alumno, "apellido_p", None),
            getattr(alumno, "apellido_m", None),
        ])).strip() or None
        numero_alumno = getattr(alumno, "pk", None)
        curp = getattr(alumno, "curp", None)
        sede = getattr(alumno, "sede", None)
        grado = getattr(alumno, "grado", None)
        programa = getattr(alumno, "programa", None)

    # Concepto / detalle a partir del PaymentRecord / Invite
    concepto = None
    pago_detalle = None
    if pr.invite:
        concepto = pr.invite.description or "Pago IUAF"
        pago_detalle = f"Invite {pr.invite.pk}"
    else:
        concepto = "Pago IUAF"
        pago_detalle = "Pago único"

    # Monto
    from decimal import Decimal as _D
    monto = _D(amount) if amount is not None else (pr.amount or _D("0"))

    # Fecha contable = hoy (o podrías mapear desde el evento)
    fecha = timezone.localdate()

    # Forma de pago estandarizada
    forma_pago = "Tarjeta (Stripe)"

    # Folio: guarda el Checkout Session id para trazabilidad
    folio = cs_id or None

    pago = PagoDiario.objects.create(
        movimiento=None,
        folio=folio,
        sede=sede,
        nombre=nombre,
        monto=monto,
        grado=grado,
        forma_pago=forma_pago,
        fecha=fecha,
        concepto=concepto,
        pago_detalle=(f"{pago_detalle} / CS:{cs_id}" if cs_id else pago_detalle),
        programa=programa,
        no_auto=pi_id or cs_id,  # idempotencia (clave de no duplicación)
        curp=curp,
        numero_alumno=numero_alumno,
        emision="Stripe",
        alumno=alumno,
        pago_oportuno=True,
    )

    # Guarda referencia en PaymentRecord.extra por si quieres mostrarlo en el admin
    pr.extra = {**(pr.extra or {}), "pago_diario_id": pago.id}
    pr.save(update_fields=["extra"])

    return pago

######################


def _handle_stripe_event(event):
    """
    Maneja eventos de Stripe y sincroniza PaymentRecord.
    Reglas clave:
      - checkout.session.completed:
          * actualiza customer/payment_intent/subscription
          * si payment_status == 'paid' -> 'paid'
          * si venía en created/failed/canceled -> 'pending' (nuevo intento)
      - payment_intent.succeeded: marca pagos únicos como 'paid' (con fallback PI->CS->PR) y crea PagoDiario
      - payment_intent.payment_failed: marca pagos únicos como 'failed' (solo si matchea ese PI)
      - invoice.paid: primera factura de subs -> 'active'
      - customer.subscription.updated/deleted: sincroniza estado de la suscripción
      - charge.refunded: pagos únicos -> 'refunded'
    """
    from .models import PaymentRecord
    import stripe as _stripe
    from decimal import Decimal

    et = event["type"]
    data = event["data"]["object"]

    def _id(v):
        if isinstance(v, dict):
            return v.get("id") or ""
        return v or ""

    # 1) checkout.session.completed
    if et == "checkout.session.completed":
        pr = _get_pr_from_session_or_metadata(data)
        if pr:
            new_pi = _id(data.get("payment_intent"))
            new_sub = _id(data.get("subscription"))
            new_cus = _id(data.get("customer"))
            payment_status = data.get("payment_status")  # 'paid' | 'unpaid' | 'no_payment_required'

            # Actualiza IDs (si Stripe generó un PI nuevo para el reintento)
            if new_pi:
                pr.payment_intent_id = new_pi
            if new_sub:
                pr.subscription_id = new_sub
            if new_cus:
                pr.customer_id = new_cus

            if pr.type == "one_time":
                if payment_status == "paid":
                    pr.status = "paid"
                else:
                    # revive si venía de 'failed', 'canceled' o 'created'
                    if pr.status in ("created", "failed", "canceled"):
                        pr.status = "pending"
            else:  # subscription
                # estado tentativo hasta invoice.paid / subscription.updated
                if pr.status in ("created", "pending"):
                    pr.status = "incomplete"

            pr.save(update_fields=["payment_intent_id", "subscription_id", "customer_id", "status"])

            # Si Stripe declara 'paid' en la Session, crea PagoDiario (idempotente)
            #if pr.type == "one_time" and payment_status == "paid":
            #    _ensure_pago_diario_for_pr(
            #        pr,
            #        pi_id=new_pi or None,
            #        cs_id=_id(data.get("id")),
            #        amount=((data.get("amount_total") or 0) / 100.0) if data.get("amount_total") else pr.amount,
            #    )
        return

    # 2) payment_intent.succeeded (pagos únicos)
    if et == "payment_intent.succeeded":
        pi_id = data.get("id", "")
        meta = data.get("metadata") or {}

        # Primero: determinístico por pr_id en metadata del PaymentIntent
        pr = None
        pr_id = meta.get("pr_id")
        if pr_id:
            pr = PaymentRecord.objects.filter(pk=pr_id).first()

        # Segundo: por payment_intent_id
        if not pr and pi_id:
            pr = PaymentRecord.objects.filter(payment_intent_id=pi_id, type="one_time").first()

        # Tercero (fallback robusto): buscar la Checkout Session por PI y luego el PR por CS
        cs_id_for_pd = None
        if not pr and pi_id:
            try:
                cs_list = _stripe.checkout.Session.list(payment_intent=pi_id, limit=1)
                if cs_list and cs_list.data:
                    cs_id_for_pd = cs_list.data[0].id
                    pr = PaymentRecord.objects.filter(checkout_session_id=cs_id_for_pd, type="one_time").first()
            except Exception:
                # no interrumpe el flujo del webhook
                pass

        if pr:
            pr.status = "paid"
            pr.payment_intent_id = pi_id or pr.payment_intent_id
            amt = data.get("amount_received")
            if isinstance(amt, int):
                try:
                    pr.amount = Decimal(amt) / Decimal(100)
                except Exception:
                    pass
            pr.save(update_fields=["status", "payment_intent_id", "amount"])

            # 👉 CREA PagoDiario aquí también (idempotente)
            # Si no calculamos antes el cs_id, intentamos obtenerlo ahora para el folio
            if not cs_id_for_pd:
                try:
                    cs_list = _stripe.checkout.Session.list(payment_intent=pi_id, limit=1)
                    if cs_list and cs_list.data:
                        cs_id_for_pd = cs_list.data[0].id
                except Exception:
                    cs_id_for_pd = None

            #_ensure_pago_diario_for_pr(
            #    pr,
            #    pi_id=pi_id,
            #    cs_id=cs_id_for_pd,
            #    amount=pr.amount,
            #)
        return

    # 2.1) payment_intent.payment_failed (marcar fallido SOLO para ese PI)
    if et == "payment_intent.payment_failed":
        pi_id = data.get("id", "")
        # solo marca failed los PR que tienen ese PI (no toques otros reintentos o pagos ya exitosos)
        qs = PaymentRecord.objects.filter(payment_intent_id=pi_id, type="one_time")
        for pr in qs:
            # no bajes un pago ya 'paid'
            if pr.status != "paid":
                pr.status = "failed"
                pr.save(update_fields=["status"])
        return

    # 3) invoice.paid (para suscripciones)
    if et == "invoice.paid":
        sub_id = _id(data.get("subscription"))
        if sub_id:
            prs = PaymentRecord.objects.filter(subscription_id=sub_id, type="subscription").order_by("created_at")
            if prs.exists():
                pr0 = prs.first()
                if pr0.status in ("incomplete", "pending", "created"):
                    pr0.status = "active"
                    pr0.save(update_fields=["status"])
        return

    # 4) customer.subscription.updated / deleted
    if et in ("customer.subscription.updated", "customer.subscription.deleted"):
        sub_id = _id(data.get("id")) or _id(data.get("subscription"))
        status = data.get("status", "")
        if sub_id:
            new_status = {
                "active": "active",
                "trialing": "active",
                "past_due": "past_due",
                "incomplete": "incomplete",
                "incomplete_expired": "canceled_sub",
                "canceled": "canceled_sub",
                "unpaid": "past_due",
            }.get(status, "active")
            prs = PaymentRecord.objects.filter(subscription_id=sub_id, type="subscription")
            for pr in prs:
                pr.status = new_status
                pr.save(update_fields=["status"])
        return

    # 5) charge.refunded (reembolsos en pagos únicos)
    if et == "charge.refunded":
        pi_id = _id(data.get("payment_intent"))
        if pi_id:
            qs = PaymentRecord.objects.filter(payment_intent_id=pi_id, type="one_time")
            for pr in qs:
                pr.status = "refunded"
                pr.save(update_fields=["status"])
        return


##############################
# cobros/views.py
from decimal import Decimal, InvalidOperation
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_protect
from django.utils import timezone
from django.conf import settings
import logging, uuid


from alumnos.models import Cargo
from .models import PaymentRecord

logger = logging.getLogger(__name__)
stripe.api_key = settings.STRIPE_SECRET_KEY


def _mk_idem(prefix="cargo"):
    return f"{prefix}:{uuid.uuid4()}:{timezone.now().isoformat()}"


@login_required
@csrf_protect
def link_pago_cargo(request, cargo_id):
    if request.method != "POST":
        return HttpResponseBadRequest("Método no permitido.")

    try:
        if not settings.STRIPE_SECRET_KEY:
            return JsonResponse({"ok": False, "error": "STRIPE_SECRET_KEY no configurada."}, status=500)

        cargo = get_object_or_404(Cargo.objects.select_related("alumno", "concepto"), pk=cargo_id)
        if not cargo.alumno:
            return JsonResponse({"ok": False, "error": "El cargo no está vinculado a un alumno."}, status=400)

        # Monto válido
        try:
            monto = Decimal(cargo.monto or 0)            
        except InvalidOperation:
            return JsonResponse({"ok": False, "error": "Monto no numérico en el cargo."}, status=400)
        if monto <= 0:
            return JsonResponse({"ok": False, "error": "El monto debe ser > 0."}, status=400)

        amount_cents = int(monto * 100)
        desc = f"{cargo.concepto.nombre if cargo.concepto_id else 'Cargo IUAF'} ({cargo.pk})"

        # === 1) Buscar PaymentRecord existente para este cargo ===
        # Si tu modelo tiene FK: 'cargo = models.OneToOneField/ForeignKey(...)', filtra por ese campo.
        pr = PaymentRecord.objects.filter(type="one_time", cargo=cargo).order_by("-created_at").first()

        # === 2) Si ya está pagado, no generes link nuevo ===
        if pr and pr.status == "paid":
            return JsonResponse({"ok": True, "already_paid": True, "message": "El cargo ya está pagado."})

        # Helper para (re)crear Session y actualizar el MISMO PR
        def _create_or_refresh_session_for(pr_obj):
            alumno = pr_obj.alumno  # (opcional, por si luego lo quieres tomar del alumno)
            email_prefill = ((getattr(alumno, "email", None) or getattr(alumno, "email_institucional", None) or "").strip() or None)

            
            session = stripe.checkout.Session.create(
                mode="payment",
                line_items=[{
                    "price_data": {
                        "currency": "mxn",
                        "product_data": {"name": desc},
                        "unit_amount": amount_cents,
                    },
                    "quantity": 1,
                }],
                success_url=settings.FRONTEND_SUCCESS_URL + "?session_id={CHECKOUT_SESSION_ID}",
                cancel_url=settings.FRONTEND_CANCEL_URL,
                client_reference_id=str(cargo.alumno_id),
                metadata={
                    "tipo": "cargo",
                    "cargo_id": str(cargo.pk),
                    "alumno_id": str(cargo.alumno_id),
                    "pr_id": str(pr_obj.pk),
                },
                payment_intent_data={
                    "metadata": {
                        "tipo": "cargo",
                        "cargo_id": str(cargo.pk),
                        "alumno_id": str(cargo.alumno_id),
                        "pr_id": str(pr_obj.pk),
                    }
                },
                customer_email=email_prefill,
                customer_creation="if_required",
                billing_address_collection="auto",

                expand=["payment_intent"],
                idempotency_key=_mk_idem("cargo"),
            )

            pr_obj.checkout_session_id = session.id or ""
            pr_obj.payment_intent_id = getattr(session, "payment_intent", None).id if getattr(session, "payment_intent", None) else ""
            pr_obj.customer_id = getattr(session, "customer", "") or pr_obj.customer_id
            pr_obj.status = "pending"
            pr_obj.amount = monto  # por si cambió el cargo
            pr_obj.extra = {**(pr_obj.extra or {}), "cargo_id": cargo.pk, "url": session.url}
            pr_obj.save(update_fields=["checkout_session_id", "payment_intent_id", "customer_id", "status", "amount", "extra"])
            return session

        # === 3) Reutilizar PR existente si hay ===
        if pr:
            sess_id = pr.checkout_session_id or ""
            if sess_id:
                try:
                    sess = stripe.checkout.Session.retrieve(sess_id)
                    sess_status = getattr(sess, "status", None)          # 'open' | 'complete' | 'expired'
                    pay_status  = getattr(sess, "payment_status", None)  # 'paid' | 'unpaid' | 'no_payment_required'

                    # a) Abierta → reutiliza el mismo link
                    if sess_status == "open":
                        url = getattr(sess, "url", None) or (pr.extra or {}).get("url")
                        if url:
                            return JsonResponse({"ok": True, "url": url, "amount": f"{monto:.2f}"})

                    # b) Completa → si pagado, marcamos y avisamos; si no, generamos nueva
                    if sess_status == "complete":
                        if pay_status == "paid":
                            pr.status = "paid"
                            pr.save(update_fields=["status"])
                            return JsonResponse({"ok": True, "already_paid": True, "message": "El cargo ya se pagó."})
                        # unpaid → nueva Session
                        new_sess = _create_or_refresh_session_for(pr)
                        return JsonResponse({"ok": True, "url": new_sess.url, "amount": f"{monto:.2f}"})

                    # c) Expirada u otro estado → nueva Session
                    new_sess = _create_or_refresh_session_for(pr)
                    return JsonResponse({"ok": True, "url": new_sess.url, "amount": f"{monto:.2f}"})

                except Exception:
                    # No se pudo recuperar → crear nueva sobre el mismo PR
                    new_sess = _create_or_refresh_session_for(pr)
                    return JsonResponse({"ok": True, "url": new_sess.url, "amount": f"{monto:.2f}"})
            else:
                # PR sin Session → crear una y actualizar el PR existente
                new_sess = _create_or_refresh_session_for(pr)
                return JsonResponse({"ok": True, "url": new_sess.url, "amount": f"{monto:.2f}"})

        # === 4) No existe PR → crearlo UNA sola vez (respeta la restricción única por cargo) ===
        pr = PaymentRecord.objects.create(
            alumno=cargo.alumno,
            cargo=cargo,              # <-- FK/OneToOne al cargo
            type="one_time",
            status="created",
            amount=monto,
            currency="MXN",
            extra={"cargo_id": cargo.pk},
        )
        sess = _create_or_refresh_session_for(pr)
        return JsonResponse({"ok": True, "url": sess.url, "amount": f"{monto:.2f}"})

    except Exception as e:
        logger.exception("Error creando/reutilizando link de pago (cargo_id=%s)", cargo_id)
        return JsonResponse({"ok": False, "error": str(e)}, status=500)


#########################################################################################

stripe.api_key = settings.STRIPE_SECRET_KEY

def checkout_success(request):
    """
    Página de 'Gracias'. No cambies estados aquí; la verdad viene del webhook.
    Solo lee el session_id para mostrar info al alumno.
    """
    session_id = request.GET.get("session_id")
    if not session_id:
        return HttpResponseBadRequest("Falta session_id.")

    # Puedes mostrar datos básicos en la pantalla:
    session = stripe.checkout.Session.retrieve(
        session_id,
        expand=["payment_intent", "subscription", "customer"]
    )

    ctx = {
        "session_id": session_id,
        "amount": (session.amount_total or 0) / 100 if getattr(session, "amount_total", None) else None,
        "currency": (session.currency or "mxn").upper() if getattr(session, "currency", None) else "MXN",
        "mode": session.mode,  # "payment" o "subscription"
        "status": getattr(session, "payment_status", None),  # 'paid' si fue pago único exitoso
    }
    return render(request, "cobros/exito.html", ctx)

def checkout_cancel(request):
    return render(request, "cobros/cancelado.html")