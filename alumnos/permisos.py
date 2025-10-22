# alumnos/permisos.py
from django.contrib.auth.models import Group

GRUPO_EDITAR_ESTATUS_ACADEMICO = "editar_estatus_academico"
GRUPO_EDITAR_ESTATUS_ADMIN = "editar_estatus_administrativo"

GRUPO_PAGOS = "pagos"
GRUPO_DOCUMENTOS = "documentos"

def user_can_edit_estatus_academico(user):
    return user.is_authenticated and (
        user.is_superuser or user.groups.filter(name=GRUPO_EDITAR_ESTATUS_ACADEMICO).exists()
    )

def user_can_edit_estatus_administrativo(user):
    return user.is_authenticated and (
        user.is_superuser or user.groups.filter(name=GRUPO_EDITAR_ESTATUS_ADMIN).exists()
    )


def user_can_view_pagos(user):
    return user.is_authenticated and (
        user.is_superuser or user.groups.filter(name=GRUPO_PAGOS).exists()
    )

def user_can_view_documentos(user):
    return user.is_authenticated and (
        user.is_superuser or user.groups.filter(name=GRUPO_DOCUMENTOS).exists()
    )


def user_can_edit_alumno(user, alumno):
    if not user.is_authenticated:
        return False
    if user.is_superuser or user.is_staff:
        return True

    profile = getattr(user, "profile", None)
    if not profile:
        return False
    if profile.puede_editar_todo:
        return True

    sede_id = getattr(getattr(alumno, "informacionEscolar", None), "sede_id", None)
    if sede_id is None:
        return False  # ajusta si quieres permitir edición sin sede
    return profile.sedes.filter(id=sede_id).exists()



def user_can_view_alumno(user, alumno):
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    if user.groups.filter(name="admisiones").exists():
        return alumno.created_by_id == user.id
    profile = getattr(user, "profile", None)
    if not profile:
        return False
    return profile.sedes.filter(id=getattr(alumno.informacionEscolar, "sede_id", None)).exists()





