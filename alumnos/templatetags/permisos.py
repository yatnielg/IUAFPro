# alumnos/templatetags/permisos.py
from django import template
register = template.Library()

#from alumnos.permisos import user_can_edit_alumno
from alumnos.permisos import user_can_edit_alumno


@register.simple_tag
def can_edit_alumno(user, alumno):
    """True/False si user puede editar a ese alumno."""
    return user_can_edit_alumno(user, alumno)


