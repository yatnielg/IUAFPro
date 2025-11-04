# cobros/utils.py
import secrets
from django.utils import timezone
from datetime import timedelta
from .models import BillingInvite

def new_token() -> str:
    return secrets.token_urlsafe(32)

def create_invite(*, alumno, amount, description="", mode="one_time", currency="MXN", interval="month", hours=72, max_uses=1, created_by=None):
    return BillingInvite.objects.create(
        alumno=alumno,
        mode=mode,
        amount=amount,
        currency=currency,
        description=description,
        interval=interval,
        token=new_token(),
        expires_at=timezone.now() + timedelta(hours=hours),
        max_uses=max_uses,
        created_by=created_by,
    )
