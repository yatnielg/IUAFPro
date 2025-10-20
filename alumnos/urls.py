# alumnos/urls.py
from django.urls import path
from .views import (
    alumnos_lista,
    alumnos_crear,
    alumnos_detalle,
    alumnos_editar,
    alumnos_crear_usuario,
    principal,
    estudiantes,
    documentos_alumno_editar,
    PagoDiarioListView,
    crear_pago_de_cargo,
    pago_exitoso,
    pago_cancelado,
    clip_webhook,
)
from alumnos import views as alumnos_views
from . import views
from django.views.decorators.csrf import csrf_exempt


urlpatterns = [    
    path("", principal, name="principal"),
    path("paraeditar", alumnos_lista, name="alumnos_lista"),
    path("principal/", principal, name="principal"),
    path("alumnos/nuevo/", alumnos_crear, name="alumnos_crear"),
    path("alumnos/<str:pk>/", alumnos_detalle, name="alumnos_detalle"),
    path("alumnos/<str:pk>/editar/", alumnos_editar, name="alumnos_editar"),
    path("alumnos/<str:pk>/crear-usuario/", alumnos_crear_usuario, name="alumnos_crear_usuario"),
    path("estudiantes", estudiantes,name="estudiantes"),
    
    path("pagos-diario/", PagoDiarioListView.as_view(), name="pagos_diario_lista"),

 
    path("alumnos/<int:pk>/documentos/", views.alumnos_documentos_editar, name="alumnos_documentos_editar"),

    path("documentos/", views.documentos_alumnos_lista, name="documentos_alumnos_lista"),

    path("alumnos/api/programa/<int:pk>/", alumnos_views.programa_info, name="alumnos_programa_info"),
    path("alumnos/api/financiamiento/<int:pk>/", alumnos_views.api_financiamiento, name="api_financiamiento"),

    path('configuracion/', views.config_panel, name='config_panel'),


    path("pagos/cargo/<int:cargo_id>/crear/", crear_pago_de_cargo, name="clip_crear_pago_cargo"),
    path("pagos/exito/<int:orden_id>/",       pago_exitoso,        name="clip_pago_exitoso"),
    path("pagos/cancelado/<int:orden_id>/",   pago_cancelado,      name="clip_pago_cancelado"),
    path("webhooks/clip/",                    clip_webhook,        name="clip_webhook"),


    path("sms/send", views.enviar_sms, name="twilio_send_sms"),
    path("wa/send", views.enviar_wa, name="twilio_send_wa"),
    path("status-callback/", csrf_exempt(views.twilio_status_callback), name="twilio_status_callback"),
]
