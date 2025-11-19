# lms/management/commands/crear_curso_demo.py
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model

from alumnos.models import Programa, Grupo
from lms.models import (
    Curso,
    Modulo,
    Leccion,
    Actividad,
    Pregunta,
    OpcionPregunta,
)


class Command(BaseCommand):
    help = "Crea un curso demo de Fundamentos de Programación con módulos, lecciones, videos, imágenes y quiz."

    def handle(self, *args, **options):
        User = get_user_model()

        # ==========================
        # 1) Buscar programa y grupo
        # ==========================
        programa = Programa.objects.order_by("id").first()
        if not programa:
            raise CommandError(
                "No hay Programas creados. Crea al menos uno en alumnos.Programa antes de ejecutar este comando."
            )

        grupo = (
            Grupo.objects.filter(programa=programa).order_by("id").first()
            or Grupo.objects.order_by("id").first()
        )

        # ==========================
        # 2) Docente demo
        # ==========================
        docente, _ = User.objects.get_or_create(
            username="docente_demo",
            defaults={
                "first_name": "Docente",
                "last_name": "Demo",
                "email": "docente.demo@example.com",
            },
        )

        # ==========================
        # 3) Curso
        # ==========================
        curso, creado = Curso.objects.get_or_create(
            codigo="FUND-PROG-DEM",
            defaults={
                "programa": programa,
                "grupo": grupo,
                "nombre": "Fundamentos de Programación (Demo)",
                "descripcion": (
                    "Curso demo de fundamentos de programación para IUAF. "
                    "Incluye lecciones con texto, imagen, video de YouTube y un cuestionario."
                ),
                "docente": docente,
                "activo": True,
            },
        )

        if not creado:
            self.stdout.write(self.style.WARNING("El curso demo ya existía, se reutilizará."))

        # ==========================
        # 4) Módulos
        # ==========================
        modulo1, _ = Modulo.objects.get_or_create(
            curso=curso,
            orden=1,
            defaults={"titulo": "Módulo 1: Introducción a la programación"},
        )
        modulo2, _ = Modulo.objects.get_or_create(
            curso=curso,
            orden=2,
            defaults={"titulo": "Módulo 2: Algoritmos y estructuras básicas"},
        )

        # ==========================
        # 5) Lecciones
        # ==========================

        # Lección 1: texto + imagen + enlace de video
        contenido_html_1 = """
<h2>¿Qué es la programación?</h2>
<p>
La programación es el proceso de crear instrucciones para que una computadora
realice tareas específicas. En este curso aprenderás los conceptos básicos
para comenzar a desarrollar tus propios programas.
</p>

<p>
<strong>Imagen ilustrativa:</strong><br>
<img src="https://images.pexels.com/photos/1181671/pexels-photo-1181671.jpeg"
     alt="Persona programando en computadora"
     style="max-width:100%;border-radius:8px;">
</p>

<p>
<strong>Video recomendado:</strong><br>
<a href="https://www.youtube.com/watch?v=8PopR3x-VMY" target="_blank">
¿Qué es programar? – Video introductorio en YouTube
</a>
</p>
        """.strip()

        leccion1, _ = Leccion.objects.get_or_create(
            modulo=modulo1,
            orden=1,
            defaults={
                "titulo": "Introducción a la programación",
                "contenido_html": contenido_html_1,
                "url_video": "https://www.youtube.com/watch?v=8PopR3x-VMY",
            },
        )

        # Lección 2: tipos de datos
        contenido_html_2 = """
<h2>Tipos de datos básicos</h2>
<ul>
  <li><strong>Enteros (int):</strong> números sin decimales, por ejemplo: 10, -3, 42.</li>
  <li><strong>Decimales (float):</strong> números con decimales, por ejemplo: 3.14, 0.5.</li>
  <li><strong>Cadenas (string):</strong> texto, por ejemplo: "Hola mundo".</li>
  <li><strong>Booleanos (bool):</strong> valores lógicos: verdadero o falso.</li>
</ul>
        """.strip()

        leccion2, _ = Leccion.objects.get_or_create(
            modulo=modulo1,
            orden=2,
            defaults={
                "titulo": "Tipos de datos",
                "contenido_html": contenido_html_2,
            },
        )

        # Lección 3: destinada al quiz
        contenido_html_3 = """
<h2>Cuestionario de repaso</h2>
<p>
Responde las siguientes preguntas para comprobar qué tanto recuerdas
sobre los conceptos vistos hasta ahora.
</p>
        """.strip()

        leccion3, _ = Leccion.objects.get_or_create(
            modulo=modulo2,
            orden=1,
            defaults={
                "titulo": "Quiz: Fundamentos de programación",
                "contenido_html": contenido_html_3,
            },
        )

        # ==========================
        # 6) Actividades
        # ==========================

        # Actividad tipo tarea
        actividad_tarea, _ = Actividad.objects.get_or_create(
            leccion=leccion1,
            titulo="Tarea: redacta qué entiendes por programación",
            tipo="tarea",
            defaults={
                "instrucciones": (
                    "En un documento de texto o en el cuadro de respuesta, "
                    "explica con tus propias palabras qué es la programación y "
                    "menciona al menos 3 ejemplos de programas que uses en tu vida diaria."
                ),
                "calificacion_maxima": 10,
            },
        )

        # Actividad tipo quiz
        actividad_quiz, _ = Actividad.objects.get_or_create(
            leccion=leccion3,
            titulo="Quiz: Fundamentos de programación",
            tipo="quiz",
            defaults={
                "instrucciones": (
                    "Responde el cuestionario. Para las preguntas de opción múltiple "
                    "selecciona solo una respuesta. Las preguntas abiertas se califican "
                    "de forma manual por el docente."
                ),
                "calificacion_maxima": 10,
            },
        )

        # ==========================
        # 7) Preguntas y opciones
        # ==========================
        # Borramos preguntas previas del quiz demo para no duplicar
        actividad_quiz.preguntas.all().delete()

        # Pregunta 1
        p1 = Pregunta.objects.create(
            actividad=actividad_quiz,
            texto="¿Qué es un algoritmo?",
            tipo="opcion_multiple",
            orden=1,
            puntaje=1,
        )
        OpcionPregunta.objects.bulk_create(
            [
                OpcionPregunta(pregunta=p1, texto="Un conjunto de instrucciones ordenadas para resolver un problema.", es_correcta=True),
                OpcionPregunta(pregunta=p1, texto="Un lenguaje de programación.", es_correcta=False),
                OpcionPregunta(pregunta=p1, texto="Un error del sistema.", es_correcta=False),
                OpcionPregunta(pregunta=p1, texto="Un archivo ejecutable.", es_correcta=False),
            ]
        )

        # Pregunta 2
        p2 = Pregunta.objects.create(
            actividad=actividad_quiz,
            texto="¿Qué significa depurar un programa?",
            tipo="opcion_multiple",
            orden=2,
            puntaje=1,
        )
        OpcionPregunta.objects.bulk_create(
            [
                OpcionPregunta(pregunta=p2, texto="Encontrar y corregir errores en el código.", es_correcta=True),
                OpcionPregunta(pregunta=p2, texto="Compilar el programa.", es_correcta=False),
                OpcionPregunta(pregunta=p2, texto="Ejecutar el programa en producción.", es_correcta=False),
                OpcionPregunta(pregunta=p2, texto="Guardar el archivo fuente.", es_correcta=False),
            ]
        )

        # Pregunta 3
        p3 = Pregunta.objects.create(
            actividad=actividad_quiz,
            texto="¿Qué tipo de dato representa valores como verdadero o falso?",
            tipo="opcion_multiple",
            orden=3,
            puntaje=1,
        )
        OpcionPregunta.objects.bulk_create(
            [
                OpcionPregunta(pregunta=p3, texto="Entero", es_correcta=False),
                OpcionPregunta(pregunta=p3, texto="Cadena de texto", es_correcta=False),
                OpcionPregunta(pregunta=p3, texto="Booleano", es_correcta=True),
                OpcionPregunta(pregunta=p3, texto="Decimal", es_correcta=False),
            ]
        )

        # Pregunta 4 (abierta)
        Pregunta.objects.create(
            actividad=actividad_quiz,
            texto="Explica con tus palabras qué es un ciclo 'while' y para qué se utiliza.",
            tipo="abierta",
            orden=4,
            puntaje=3,
        )

        # Pregunta 5 (abierta)
        Pregunta.objects.create(
            actividad=actividad_quiz,
            texto="Describe un ejemplo real donde usarías una función en programación.",
            tipo="abierta",
            orden=5,
            puntaje=4,
        )

        # ==========================
        # Listo
        # ==========================
        self.stdout.write(self.style.SUCCESS("Curso demo de Fundamentos de Programación creado correctamente."))
