# alumnos/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Alumno
from .emails import enviar_bienvenida_alumno

@receiver(post_save, sender=Alumno)
def alumno_bienvenida(sender, instance: Alumno, created, **kwargs):
    if created:
        enviar_bienvenida_alumno(instance)
