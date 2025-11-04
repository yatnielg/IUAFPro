from django.urls import path
from . import views

app_name = 'cobros'

urlpatterns = [
    path("pagar/<str:token>/", views.pagar_con_token, name="pagar_con_token"),
    path("webhooks/stripe/", views.stripe_webhook, name="stripe_webhook"),
    path("link-pago/cargo/<int:cargo_id>/", views.link_pago_cargo, name="link_pago_cargo"),  # 👈 nuevo

    path("exito/", views.checkout_success, name="checkout_success"),
    path("cancelado/", views.checkout_cancel, name="checkout_cancel"),
]
