# cobros/services.py
import stripe
import hashlib
from decimal import Decimal
from django.conf import settings

from .models import StripeCustomer, PaymentRecord

stripe.api_key = settings.STRIPE_SECRET_KEY


def _get_or_create_customer(alumno):
    """
    Devuelve el ID de cliente de Stripe para el alumno; lo crea si no existe.
    """
    sc = getattr(alumno, "stripe_customer", None)
    if sc:
        return sc.stripe_customer_id

    customer = stripe.Customer.create(
        name=f"{alumno.nombre} {alumno.apellido_p or ''} {alumno.apellido_m or ''}".strip(),
        email=alumno.email_preferido or None,
        metadata={"alumno_id": str(alumno.pk)},
    )
    StripeCustomer.objects.create(alumno=alumno, stripe_customer_id=customer.id)
    return customer.id


def create_checkout_for_invite(invite, request=None):
    """
    Crea una Checkout Session en Stripe (pago único o suscripción) para un BillingInvite
    y devuelve (url, PaymentRecord).

    - Crea el PaymentRecord ANTES de ir a Stripe.
    - Pasa metadata.pr_id y payment_intent_data.metadata.pr_id (evita race conditions).
    - Usa idempotency_key como opción de la llamada (no dentro del payload).
    - Limita longitud de idempotency_key para DB (64) y Stripe (<=255).
    """
    customer_id = _get_or_create_customer(invite.alumno)

    # Idempotencia estable basada en el token del invite
    idem_raw = f"invite:{invite.token}"
    idem_hdr = idem_raw[:255]  # Stripe
    idem_db = hashlib.sha256(idem_raw.encode("utf-8")).hexdigest()[:64]  # DB

    success_url = settings.FRONTEND_SUCCESS_URL + "?session_id={CHECKOUT_SESSION_ID}"
    cancel_url = settings.FRONTEND_CANCEL_URL
    amount_cents = int(Decimal(invite.amount) * 100)

    # 1) Crear PaymentRecord en "created"
    pr = PaymentRecord.objects.create(
        alumno=invite.alumno,
        invite=invite,
        type="one_time" if invite.mode == "one_time" else "subscription",
        status="created",
        amount=invite.amount,
        currency=invite.currency,
    )

    if invite.mode == "one_time":
        session = stripe.checkout.Session.create(
            mode="payment",
            customer=customer_id,
            line_items=[{
                "price_data": {
                    "currency": invite.currency.lower(),
                    "product_data": {"name": invite.description or "Pago único"},
                    "unit_amount": amount_cents,
                },
                "quantity": 1,
            }],
            success_url=success_url,
            cancel_url=cancel_url,
            client_reference_id=str(invite.id),
            metadata={
                "invite_id": str(invite.id),
                "alumno_id": str(invite.alumno_id),
                "mode": invite.mode,
                "pr_id": str(pr.pk),
            },
            # CLAVE: poner también metadata en el PaymentIntent para que
            # payment_intent.succeeded pueda enlazar incluso si llega antes.
            payment_intent_data={
                "metadata": {
                    "pr_id": str(pr.pk),
                    "invite_id": str(invite.id),
                    "alumno_id": str(invite.alumno_id),
                }
            },
            automatic_tax={"enabled": False},
            allow_promotion_codes=False,
            expand=["payment_intent"],
            idempotency_key=idem_hdr,
        )

        pr.checkout_session_id = session.id or ""
        pr.payment_intent_id = (getattr(session, "payment_intent", None).id if getattr(session, "payment_intent", None) else "")
        pr.customer_id = customer_id
        pr.idempotency_key = idem_db
        pr.status = "pending"  # se confirmará con payment_intent.succeeded
        pr.extra = {"url": session.url}
        pr.save(update_fields=[
            "checkout_session_id",
            "payment_intent_id",
            "customer_id",
            "idempotency_key",
            "status",
            "extra",
        ])
        return session.url, pr

    # Suscripción (recurrente)
    session = stripe.checkout.Session.create(
        mode="subscription",
        customer=customer_id,
        line_items=[{
            "price_data": {
                "currency": invite.currency.lower(),
                "recurring": {"interval": invite.interval},
                "product_data": {"name": invite.description or "Suscripción"},
                "unit_amount": amount_cents,
            },
            "quantity": 1,
        }],
        success_url=success_url,
        cancel_url=cancel_url,
        client_reference_id=str(invite.id),
        metadata={
            "invite_id": str(invite.id),
            "alumno_id": str(invite.alumno_id),
            "mode": invite.mode,
            "pr_id": str(pr.pk),
        },
        automatic_tax={"enabled": False},
        allow_promotion_codes=False,
        expand=["subscription"],
        idempotency_key=idem_hdr,
    )

    pr.checkout_session_id = session.id or ""
    pr.subscription_id = (getattr(session, "subscription", None).id if getattr(session, "subscription", None) else "")
    pr.customer_id = customer_id
    pr.idempotency_key = idem_db
    pr.status = "incomplete"  # pasará a active con invoice.paid / subscription.updated
    pr.extra = {"url": session.url}
    pr.save(update_fields=[
        "checkout_session_id",
        "subscription_id",
        "customer_id",
        "idempotency_key",
        "status",
        "extra",
    ])
    return session.url, pr


def create_one_time_checkout_for_cargo(
    *, alumno, amount, currency="MXN", description="", idempotency_key="", metadata=None
):
    """
    Crea una Stripe Checkout Session de PAGO ÚNICO para un cargo específico.
    Devuelve (url, PaymentRecord).

    - Crea PaymentRecord antes de la llamada a Stripe.
    - Pasa metadata.pr_id y payment_intent_data.metadata.pr_id (evita race conditions).
    """
    metadata = metadata or {}
    customer_id = _get_or_create_customer(alumno)
    amount_cents = int(Decimal(amount) * 100)

    # 1) PR en "created"
    pr = PaymentRecord.objects.create(
        alumno=alumno,
        invite=None,
        type="one_time",
        status="created",
        amount=Decimal(amount),
        currency=currency,
    )

    # 2) Crear Session con pr_id en metadata y en payment_intent_data.metadata
    session = stripe.checkout.Session.create(
        mode="payment",
        customer=customer_id,
        line_items=[{
            "price_data": {
                "currency": currency.lower(),
                "product_data": {"name": description or "Pago IUAF"},
                "unit_amount": amount_cents,
            },
            "quantity": 1,
        }],
        success_url=settings.FRONTEND_SUCCESS_URL + "?session_id={CHECKOUT_SESSION_ID}",
        cancel_url=settings.FRONTEND_CANCEL_URL,
        client_reference_id=str(alumno.pk),
        metadata={**metadata, "pr_id": str(pr.pk), "alumno_id": str(alumno.pk)},
        payment_intent_data={
            "metadata": {**metadata, "pr_id": str(pr.pk), "alumno_id": str(alumno.pk)}
        },
        automatic_tax={"enabled": False},
        allow_promotion_codes=False,
        expand=["payment_intent"],
        idempotency_key=idempotency_key or None,
    )

    # 3) Rellenar PR con IDs reales de Stripe y marcar "pending"
    pr.checkout_session_id = session.id or ""
    pr.payment_intent_id = (getattr(session, "payment_intent", None).id if getattr(session, "payment_intent", None) else "")
    pr.customer_id = customer_id
    pr.idempotency_key = idempotency_key or ""
    pr.status = "pending"
    pr.extra = {"url": session.url, "metadata": metadata}
    pr.save(update_fields=[
        "checkout_session_id",
        "payment_intent_id",
        "customer_id",
        "idempotency_key",
        "status",
        "extra",
    ])

    return session.url, pr
