# lms/urls.py
from django.urls import path
from . import views

app_name = "lms"

urlpatterns = [
    path("mis-cursos/", views.mis_cursos, name="mis_cursos"),
    path("curso/<int:pk>/", views.curso_detalle, name="curso_detalle"),
    path("actividad/<int:pk>/", views.actividad_detalle, name="actividad_detalle"),


    path("actividad/<int:pk>/respuestas/", views.actividad_respuestas, name="actividad_respuestas"),

    path("admin/cursos/", views.cursos_todos, name="cursos_todos"),
]
