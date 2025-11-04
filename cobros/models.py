from django.db import models
from django.conf import settings
from django.utils import timezone
from decimal import Decimal
from django.core.validators import MinValueValidator

# Si tu modelo Alumno está en otra app, ajusta la importación:
from alumnos.models import Alumno

class StripeCustomer(models.Model):
    alumno = models.OneToOneField(Alumno, on_delete=models.CASCADE, related_name="stripe_customer")
    stripe_customer_id = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.alumno_id} -> {self.stripe_customer_id}"

class BillingInvite(models.Model):
    MODE_CHOICES = (("one_time", "Pago único"), ("recurring", "Recurrente"))
    CURRENCY_CHOICES = (("MXN", "MXN"), ("USD", "USD"))

    alumno = models.ForeignKey(Alumno, on_delete=models.CASCADE, related_name="billing_invites")
    # Datos de cobro
    mode = models.CharField(max_length=16, choices=MODE_CHOICES, default="one_time")
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("1.00"))])
    currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES, default="MXN")
    description = models.CharField(max_length=255, blank=True)
    # Para recurrente
    interval = models.CharField(max_length=16, default="month")  # 'day'|'week'|'month'|'year'

    # Control del link temporal
    token = models.CharField(max_length=64, unique=True)  # lo generarás aleatorio
    expires_at = models.DateTimeField()
    max_uses = models.PositiveIntegerField(default=1)
    uses = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    # Auditoría
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    def is_valid(self) -> bool:
        if not self.is_active:
            return False
        if self.expires_at and timezone.now() > self.expires_at:
            return False
        if self.max_uses and self.uses >= self.max_uses:
            return False
        return True

    def __str__(self):
        return f"{self.alumno_id} {self.mode} {self.amount} {self.currency} (ok:{self.is_valid()})"

class PaymentRecord(models.Model):
    TYPE_CHOICES = (("one_time", "Pago único"), ("subscription", "Suscripción"))
    STATUS_CHOICES = (
        ("created", "Creado"),
        ("pending", "Pendiente"),
        ("paid", "Pagado"),
        ("failed", "Fallido"),
        ("canceled", "Cancelado"),
        ("refunded", "Reembolsado"),
        ("active", "Activo"),      # subs
        ("incomplete", "Incompleto"),  # subs
        ("past_due", "Atrasado"),  # subs
        ("canceled_sub", "Cancelada")  # subs
    )

    alumno = models.ForeignKey(Alumno, on_delete=models.SET_NULL, null=True, related_name="payment_records")
    invite = models.ForeignKey(BillingInvite, on_delete=models.SET_NULL, null=True, blank=True, related_name="payments")
    type = models.CharField(max_length=16, choices=TYPE_CHOICES)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="created")

    amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3, default="MXN")

    # IDs Stripe
    checkout_session_id = models.CharField(max_length=255, blank=True, db_index=True)
    payment_intent_id   = models.CharField(max_length=255, blank=True, db_index=True)
    subscription_id     = models.CharField(max_length=255, blank=True, db_index=True)
    customer_id         = models.CharField(max_length=255, blank=True, db_index=True)
    idempotency_key     = models.CharField(max_length=255, blank=True, db_index=True)


    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    cargo = models.OneToOneField('alumnos.Cargo', null=True, blank=True, on_delete=models.SET_NULL, related_name="payment_record")

    extra = models.JSONField(null=True, blank=True)

    def __str__(self):        
        return f"{self.type}:{self.status} alumno={self.alumno_id} session={self.checkout_session_id}"
    

    def save(self, *args, **kwargs):
        """
        Si el status cambia a 'paid', crea (si no existe) un PagoDiario ligado (OneToOne).
        - Idempotente por la OneToOne y por 'no_auto' = payment_intent_id (truncado a 64).
        - Evita el choque insert + update_fields.
        """
        # Evita combinación inválida: insert + update_fields
        if kwargs.get("force_insert") and kwargs.get("update_fields"):
            kwargs.pop("update_fields", None)

        creating = self.pk is None

        # Si estamos actualizando, captura el status anterior
        old_status = None
        if not creating:
            try:
                old_status = type(self).objects.only("status").get(pk=self.pk).status
            except type(self).DoesNotExist:
                pass

        res = super().save(*args, **kwargs)

        # Si status pasó a 'paid' -> crear PagoDiario (idempotente)
        if (creating and self.status == "paid") or (old_status != "paid" and self.status == "paid"):
            try:
                # Import local para evitar ciclos
                from alumnos.models import PagoDiario
                # OneToOne asegura idempotencia; si ya existe, no se duplica
                if not hasattr(self, "pago_diario") or self.pago_diario is None:
                    # Ajustes de longitudes de campos cortos
                    folio = (self.checkout_session_id or "")[:32]  # campo folio=32
                    no_auto = (self.payment_intent_id or self.checkout_session_id or "")[:64]  # campo no_auto=64

                    # Nombre bonito (si existe)
                    alumno = self.alumno
                    nombre = None
                    if alumno:
                        nombre = " ".join(filter(None, [
                            getattr(alumno, "nombre", None),
                            getattr(alumno, "apellido_p", None),
                            getattr(alumno, "apellido_m", None),
                        ])).strip() or None

                    # Concepto/detalle
                    if self.invite_id and getattr(self, "invite", None):
                        concepto = self.cargo.concepto if self.cargo else f"Invite {self.invite_id}"
                        pago_detalle = f"Invite {self.invite_id} / CS:{''}"
                    else:
                        concepto = self.cargo.concepto if self.cargo else "Pago único"
                        pago_detalle = f"Pago único / CS:{''}"

                    # Crear (idempotente por OneToOne); si ya existe no rompe
                    PagoDiario.objects.get_or_create(
                        payment_record=self,
                        defaults={
                            "movimiento": None,
                            "folio": folio or None,
                            "sede": getattr(getattr(alumno, "informacionEscolar", None), "sede", None) and getattr(alumno.informacionEscolar.sede, "nombre", None) or None,
                            "nombre": nombre,
                            "monto": self.amount,
                            "grado": getattr(getattr(alumno, "informacionEscolar", None), "grupo", None),
                            "forma_pago": "Tarjeta (Stripe)",
                            "fecha": timezone.localdate(),
                            "concepto": concepto,
                            "pago_detalle": (pago_detalle or None)[:200],
                            "programa": getattr(getattr(alumno, "informacionEscolar", None), "programa", None) and getattr(alumno.informacionEscolar.programa, "nombre", None) or None,
                            "no_auto": no_auto or None,
                            "curp": getattr(alumno, "curp", None),
                            "numero_alumno": getattr(alumno, "pk", None),
                            "emision": "Stripe",
                            "alumno": alumno,
                            "pago_oportuno": True,
                        },
                    )
            except Exception:
                # No interrumpas el flujo de guardado del PaymentRecord por fallas en PagoDiario.
                pass

        return res

class WebhookEvent(models.Model):
    provider_event_id = models.CharField(max_length=64, unique=True)
    event_type = models.CharField(max_length=80)
    payload = models.JSONField()
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    error = models.TextField(blank=True)

    def __str__(self):
        return f"{self.event_type} ({self.provider_event_id})"
