from django.contrib import admin

# Register your models here.
# lms/admin.py
from django.contrib import admin
from .models import Curso, Modulo, Leccion, Actividad, Entrega, AccesoCurso

admin.site.register(Curso)
admin.site.register(Modulo)
admin.site.register(Leccion)
admin.site.register(Actividad)
admin.site.register(Entrega)
admin.site.register(AccesoCurso)
