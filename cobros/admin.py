from django.contrib import admin
from .models import StripeCustomer, BillingInvite, PaymentRecord, WebhookEvent

@admin.register(StripeCustomer)
class SCAdmin(admin.ModelAdmin):
    list_display = ("alumno", "stripe_customer_id", "created_at")
    search_fields = ("alumno__numero_estudiante", "stripe_customer_id")

@admin.register(BillingInvite)
class BIAdmin(admin.ModelAdmin):
    list_display = ("alumno", "mode", "amount", "currency", "token", "is_active", "uses", "max_uses", "expires_at")
    search_fields = ("alumno__numero_estudiante", "token", "description")
    list_filter = ("mode", "currency", "is_active")

@admin.register(PaymentRecord)
class PRAdmin(admin.ModelAdmin):
    list_display = ("alumno", "type", "status", "amount", "currency", "checkout_session_id", "subscription_id", "created_at")
    search_fields = ("checkout_session_id", "payment_intent_id", "subscription_id", "alumno__numero_estudiante")
    list_filter = ("type", "status", "currency")

@admin.register(WebhookEvent)
class WEAdmin(admin.ModelAdmin):
    list_display = ("provider_event_id", "event_type", "received_at", "processed_at")
    search_fields = ("provider_event_id", "event_type")
