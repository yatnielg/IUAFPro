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
)
from alumnos import views as alumnos_views
from . import views

urlpatterns = [    
    path("", principal, name="principal"),
    path("paraeditar", alumnos_lista, name="alumnos_lista"),
    path("principal/", principal, name="principal"),
    path("alumnos/nuevo/", alumnos_crear, name="alumnos_crear"),
    path("alumnos/<str:pk>/", alumnos_detalle, name="alumnos_detalle"),
    path("alumnos/<str:pk>/editar/", alumnos_editar, name="alumnos_editar"),
    path("alumnos/<str:pk>/crear-usuario/", alumnos_crear_usuario, name="alumnos_crear_usuario"),
    path("estudiantes", estudiantes,name="estudiantes"),
    path( "alumnos/<str:numero_estudiante>/documentos/",documentos_alumno_editar,name="alumnos_documentos_editar"),
    path("pagos-diario/", PagoDiarioListView.as_view(), name="pagos_diario_lista"),
    path("alumnos/<int:pk>/documentos/", views.alumnos_documentos_editar, name="alumnos_documentos_editar"),
    path("alumnos/api/programa/<int:pk>/", alumnos_views.programa_info, name="alumnos_programa_info"),
    path("alumnos/api/financiamiento/<int:pk>/", alumnos_views.api_financiamiento, name="api_financiamiento"),
]
