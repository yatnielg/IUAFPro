from django.apps import AppConfig


class AlumnosConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'alumnos'

    #def ready(self):
    #    from . import signals  # noqa: F401