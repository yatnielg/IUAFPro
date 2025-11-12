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

app_name = "alumnos"

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
    path("alumnos/api/curp-lookup/", views.api_curp_lookup, name="api_curp_lookup"),
    path("alumnos/<int:pk>/documentos/", views.alumnos_documentos_editar, name="alumnos_documentos_editar"),
    path("documentos/", views.documentos_alumnos_lista, name="documentos_alumnos_lista"),
    path("alumnos/api/programa/<int:pk>/", alumnos_views.programa_info, name="alumnos_programa_info"),
    path("alumnos/api/financiamiento/<int:pk>/", alumnos_views.api_financiamiento, name="api_financiamiento"),
    path('configuracion/', views.config_panel, name='config_panel'),
    path("pagos/cargo/<int:cargo_id>/crear/", crear_pago_de_cargo, name="clip_crear_pago_cargo"),
    path("pagos/exito/<int:orden_id>/",       pago_exitoso,        name="clip_pago_exitoso"),
    path("pagos/cancelado/<int:orden_id>/",   pago_cancelado,      name="clip_pago_cancelado"),
    path("webhooks/clip/",                    clip_webhook,        name="clip_webhook"),
    path("alumnos/<int:alumno_id>/documentos/pdf/", views.documentos_unificados_pdf, name="alumnos_documentos_pdf"),
    path("sms/send", views.enviar_sms, name="twilio_send_sms"),
    path("wa/send", views.enviar_wa, name="twilio_send_wa"),
    path("status-callback/", csrf_exempt(views.twilio_status_callback), name="twilio_status_callback"),
    path("tools/leer-google-sheet/", views.run_leer_google_sheet, name="run_leer_google_sheet"),
    path("banco/movimientos/", views.MovimientoBancoListView.as_view(), name="movimientos_banco_lista"),
    path("banco/movimientos/run-update/", views.run_movimientos_banco_update, name="movimientos_banco_update"),
    path("uploads/<str:token>/", views.public_upload, name="public_upload"),
    path("alumnos/<int:pk>/generar-enlace/", views.generar_enlace_subida, name="generar_enlace_subida"),
    path("alumnos/<int:pk>/generar-enlace-json/",views.generar_enlace_subida_json,name="generar_enlace_subida_json"),
    path("banco/abonos/", views.movimientos_abonos_pendientes, name="movimientos_abonos_pendientes"),
    path("banco/conciliar/<int:mov_id>/", views.conciliar_movimiento, name="conciliar_movimiento"),
    path("banco/movimientos/<int:pk>/set-nds/",views.set_nombre_detectado_save,name="mov_set_nds"),
    path('movimiento/<int:mov_id>/deshacer/', views.deshacer_conciliacion, name='mov_deshacer_conciliacion'),
    path("pagos/<int:pk>/recibo.pdf", views.pago_recibo_pdf, name="pago_recibo_pdf"),
    path("reportes/recibo2/", views.recibo2_from_excel, name="recibo2_from_excel"),
    path("<int:pk>/recibo/", views.recibo_pago_carta, name="recibo_carta"),
    path('estado-cuenta/<int:numero_estudiante>/', views.estado_cuenta, name='estado_cuenta'),
    path('estado-cuenta/', views.estado_cuenta, name='estado_cuenta_demo'),
    path("alumnos/api/financiamientos/", views.api_financiamientos_list, name="api_financiamientos_list"),
    path("alumnos/<int:numero_estudiante>/generar_cargos/",alumnos_views.generar_cargos_mensuales,name="generar_cargos_mensuales"),
    path("alumnos/cargos/pendientes/", alumnos_views.cargos_pendientes_todos, name="cargos_pendientes_todos"),
    path("alumnos/<int:pk>/cargos/nuevo/", views.cargo_crear, name="cargo_crear"),
    path("alumnos/<int:alumno_pk>/cargos/<int:cargo_id>/editar/", views.cargo_editar, name="cargo_editar"), 
    path('alumnos/<int:alumno_id>/cargos/<int:cargo_id>/eliminar/', views.cargo_eliminar, name='cargo_eliminar'),
    path('alumnos/<int:alumno_id>/saldos/<str:concepto_codigo>/', views.saldos_por_concepto_view, name='saldos_por_concepto'),
    path('alumnos/<int:alumno_id>/cargos-con-saldo/', views.cargos_con_saldo_view, name='cargos_con_saldo'),
    path("alumnos/<int:alumno_id>/enviar-bienvenida/", views.enviar_bienvenida_estatica, name="enviar_bienvenida_estatica"),
    path("alumnos/<int:alumno_id>/expediente/", views.expediente_maestria_view, name="expediente_maestria"),
    path("alumnos/<int:alumno_id>/carta/", views.carta_inscripcion_view, name="alumno_carta"),
    path("alumnos/<int:alumno_id>/carta/pdf/", views.carta_inscripcion_pdf_view, name="alumno_carta_pdf"),


    #path("alumnos/pagos/<int:pk>/enviar-recibo-email/", views.enviar_recibo_pago_email, name="enviar_recibo_pago_email"),

    path("alumnos/pagos/<int:pago_id>/enviar-recibo-con-pdf/", views.enviar_recibo_email_con_pdf, name="enviar_recibo_con_pdf"),


    path("alumnos/<int:pk>/boleta/", views.boleta_calificaciones, name="alumno_boleta"),



]
