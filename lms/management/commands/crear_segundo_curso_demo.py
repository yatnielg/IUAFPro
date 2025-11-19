# lms/management/commands/crear_segundo_curso_demo.py
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
    help = "Crea un segundo curso demo (Introducción a Python) con módulos, lecciones y quiz."

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
        # 2) Docente demo (reutilizamos o creamos)
        # ==========================
        docente, _ = User.objects.get_or_create(
            username="docente_demo_python",
            defaults={
                "first_name": "Docente",
                "last_name": "Python",
                "email": "docente.python@example.com",
            },
        )

        # ==========================
        # 3) Curso
        # ==========================
        curso, creado = Curso.objects.get_or_create(
            codigo="INTRO-PY-DEM",
            defaults={
                "programa": programa,
                "grupo": grupo,
                "nombre": "Introducción a Python (Demo)",
                "descripcion": (
                    "Curso demo de introducción a Python. "
                    "Incluye lecciones con texto, ejemplos de código y un cuestionario."
                ),
                "docente": docente,
                "activo": True,
            },
        )

        if not creado:
            self.stdout.write(self.style.WARNING("El curso INTRO-PY-DEM ya existía, se reutilizará."))

        # ==========================
        # 4) Módulos
        # ==========================
        modulo1, _ = Modulo.objects.get_or_create(
            curso=curso,
            orden=1,
            defaults={"titulo": "Módulo 1: Primeros pasos con Python"},
        )
        modulo2, _ = Modulo.objects.get_or_create(
            curso=curso,
            orden=2,
            defaults={"titulo": "Módulo 2: Estructuras de control en Python"},
        )

        # ==========================
        # 5) Lecciones
        # ==========================

        # Lección 1: instalación y primer script
        contenido_html_1 = """
<h2>Instalación de Python y primer programa</h2>
<p>
Python es un lenguaje de programación muy utilizado en ciencia de datos,
desarrollo web, automatización y muchas otras áreas.
</p>

<ol>
  <li>Descarga Python desde <a href="https://www.python.org" target="_blank">python.org</a>.</li>
  <li>Instálalo en tu sistema siguiendo el asistente.</li>
  <li>Abre tu editor favorito (VSCode, PyCharm, etc.).</li>
  <li>Crea un archivo <code>hola.py</code> con el siguiente contenido:</li>
</ol>

<pre><code>print("Hola, mundo desde Python!")</code></pre>

<p>
Ejecuta el programa y verifica que se muestre el mensaje en la consola.
</p>
        """.strip()

        leccion1, _ = Leccion.objects.get_or_create(
            modulo=modulo1,
            orden=1,
            defaults={
                "titulo": "Instalación y primer programa",
                "contenido_html": contenido_html_1,
                "url_video": "https://www.youtube.com/watch?v=_uQrJ0TkZlc",  # video típico de intro a Python
            },
        )

        # Lección 2: variables y tipos
        contenido_html_2 = """
<h2>Variables y tipos de datos en Python</h2>
<p>
En Python no necesitas declarar el tipo de la variable explícitamente.
El intérprete lo infiere a partir del valor.
</p>

<pre><code>nombre = "Ana"
edad = 25
pi = 3.1416
es_estudiante = True

print(nombre, edad, pi, es_estudiante)</code></pre>

<ul>
  <li><strong>str</strong>: cadenas de texto.</li>
  <li><strong>int</strong>: números enteros.</li>
  <li><strong>float</strong>: números con decimales.</li>
  <li><strong>bool</strong>: valores lógicos True/False.</li>
</ul>
        """.strip()

        leccion2, _ = Leccion.objects.get_or_create(
            modulo=modulo1,
            orden=2,
            defaults={
                "titulo": "Variables y tipos de datos en Python",
                "contenido_html": contenido_html_2,
            },
        )

        # Lección 3: destinada al quiz
        contenido_html_3 = """
<h2>Quiz: conceptos básicos de Python</h2>
<p>
Responde el siguiente cuestionario para reforzar tu comprensión de los
conceptos fundamentales de Python.
</p>
        """.strip()

        leccion3, _ = Leccion.objects.get_or_create(
            modulo=modulo2,
            orden=1,
            defaults={
                "titulo": "Quiz: Básicos de Python",
                "contenido_html": contenido_html_3,
            },
        )

        # ==========================
        # 6) Actividades
        # ==========================

        # Actividad tipo tarea
        actividad_tarea, _ = Actividad.objects.get_or_create(
            leccion=leccion2,
            titulo="Tarea: crea tu propio script en Python",
            tipo="tarea",
            defaults={
                "instrucciones": (
                    "Escribe un script en Python que pida al usuario su nombre y edad, "
                    "y luego muestre un mensaje: 'Hola, &lt;nombre&gt;, tienes &lt;edad&gt; años'. "
                    "Sube el archivo .py o copia el código en el cuadro de respuesta."
                ),
                "calificacion_maxima": 10,
            },
        )

        # Actividad tipo quiz
        actividad_quiz, _ = Actividad.objects.get_or_create(
            leccion=leccion3,
            titulo="Quiz: Introducción a Python",
            tipo="quiz",
            defaults={
                "instrucciones": (
                    "Responde el cuestionario sobre conceptos básicos de Python. "
                    "Las preguntas de opción múltiple se califican de forma automática; "
                    "las abiertas, de forma manual por el docente."
                ),
                "calificacion_maxima": 10,
            },
        )

        # ==========================
        # 7) Preguntas y opciones
        # ==========================
        # Borramos preguntas previas del quiz para no duplicar
        actividad_quiz.preguntas.all().delete()

        # Pregunta 1
        p1 = Pregunta.objects.create(
            actividad=actividad_quiz,
            texto="¿Qué instrucción se usa para mostrar información en pantalla en Python?",
            tipo="opcion_multiple",
            orden=1,
            puntaje=1,
        )
        OpcionPregunta.objects.bulk_create(
            [
                OpcionPregunta(pregunta=p1, texto="echo()", es_correcta=False),
                OpcionPregunta(pregunta=p1, texto="console.log()", es_correcta=False),
                OpcionPregunta(pregunta=p1, texto="print()", es_correcta=True),
                OpcionPregunta(pregunta=p1, texto="mostrar()", es_correcta=False),
            ]
        )

        # Pregunta 2
        p2 = Pregunta.objects.create(
            actividad=actividad_quiz,
            texto="¿Cuál de los siguientes es un comentario de una sola línea en Python?",
            tipo="opcion_multiple",
            orden=2,
            puntaje=1,
        )
        OpcionPregunta.objects.bulk_create(
            [
                OpcionPregunta(pregunta=p2, texto="// Esto es un comentario", es_correcta=False),
                OpcionPregunta(pregunta=p2, texto="/* Esto es un comentario */", es_correcta=False),
                OpcionPregunta(pregunta=p2, texto="# Esto es un comentario", es_correcta=True),
                OpcionPregunta(pregunta=p2, texto="-- Esto es un comentario", es_correcta=False),
            ]
        )

        # Pregunta 3
        p3 = Pregunta.objects.create(
            actividad=actividad_quiz,
            texto="¿Qué tipo de dato produce la expresión: 5 &gt; 3 en Python?",
            tipo="opcion_multiple",
            orden=3,
            puntaje=1,
        )
        OpcionPregunta.objects.bulk_create(
            [
                OpcionPregunta(pregunta=p3, texto="int", es_correcta=False),
                OpcionPregunta(pregunta=p3, texto="str", es_correcta=False),
                OpcionPregunta(pregunta=p3, texto="bool", es_correcta=True),
                OpcionPregunta(pregunta=p3, texto="float", es_correcta=False),
            ]
        )

        # Pregunta 4 (abierta)
        Pregunta.objects.create(
            actividad=actividad_quiz,
            texto="Explica con tus palabras qué es una variable en Python y cómo se usa.",
            tipo="abierta",
            orden=4,
            puntaje=3,
        )

        # Pregunta 5 (abierta)
        Pregunta.objects.create(
            actividad=actividad_quiz,
            texto="Describe un ejemplo donde usarías una estructura condicional if en un programa real.",
            tipo="abierta",
            orden=5,
            puntaje=4,
        )

        # ==========================
        # Listo
        # ==========================
        self.stdout.write(self.style.SUCCESS("Segundo curso demo 'Introducción a Python' creado correctamente."))
#python manage.py crear_segundo_curso_demo
