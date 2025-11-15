# academico/urls.py
from django.urls import path
from . import views

app_name = "academico"

urlpatterns = [
    path("listados/", views.listados_list, name="listados_list"),
    path("listados/<int:pk>/", views.listado_detalle, name="listado_detalle"),
    path("listados/item/<int:pk>/calificaciones/", views.calificaciones_item, name="calificaciones_item"),
    path("materias-profesores/", views.materias_profesores_list, name="materias_profesores_list"),

    path("profesores/", views.profesores_list, name="profesores_list"),
]
