# alumnos/permisos.py
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
