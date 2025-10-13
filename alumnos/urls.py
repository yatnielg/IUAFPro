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
)

urlpatterns = [
    
    path("", principal, name="principal"),
    path("paraeditar", alumnos_lista, name="alumnos_lista"),
    path("principal/", principal, name="principal"),
    path("alumnos/nuevo/", alumnos_crear, name="alumnos_crear"),
    path("alumnos/<str:pk>/", alumnos_detalle, name="alumnos_detalle"),
    path("alumnos/<str:pk>/editar/", alumnos_editar, name="alumnos_editar"),
    path("alumnos/<str:pk>/crear-usuario/", alumnos_crear_usuario, name="alumnos_crear_usuario"),
    path("estudiantes", estudiantes,name="estudiantes"),


]
