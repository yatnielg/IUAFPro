# lms/management/commands/crear_tercer_curso_demo.py
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
    help = "Crea un tercer curso demo (Algoritmos y Lógica de Programación) con módulos, lecciones y quiz."

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
        # 2) Docente demo (nuevo o reutilizado)
        # ==========================
        docente, _ = User.objects.get_or_create(
            username="docente_demo_logica",
            defaults={
                "first_name": "Docente",
                "last_name": "Lógica",
                "email": "docente.logica@example.com",
            },
        )

        # ==========================
        # 3) Curso
        # ==========================
        curso, creado = Curso.objects.get_or_create(
            codigo="ALGO-DEM",
            defaults={
                "programa": programa,
                "grupo": grupo,
                "nombre": "Algoritmos y Lógica de Programación (Demo)",
                "descripcion": (
                    "Curso demo de algoritmos y lógica de programación. "
                    "Introduce el pensamiento algorítmico, los diagramas de flujo "
                    "y el uso de pseudocódigo para resolver problemas."
                ),
                "docente": docente,
                "activo": True,
            },
        )

        if not creado:
            self.stdout.write(self.style.WARNING("El curso ALGO-DEM ya existía, se reutilizará."))

        # ==========================
        # 4) Módulos
        # ==========================
        modulo1, _ = Modulo.objects.get_or_create(
            curso=curso,
            orden=1,
            defaults={"titulo": "Módulo 1: Pensamiento algorítmico"},
        )
        modulo2, _ = Modulo.objects.get_or_create(
            curso=curso,
            orden=2,
            defaults={"titulo": "Módulo 2: Pseudocódigo y diagramas de flujo"},
        )

        # ==========================
        # 5) Lecciones
        # ==========================

        # Lección 1: ¿qué es un algoritmo?
        contenido_html_1 = """
<h2>¿Qué es un algoritmo?</h2>
<p>
Un algoritmo es un conjunto de pasos ordenados y finitos que permiten resolver
un problema o realizar una tarea. Los algoritmos están presentes en la vida diaria:
seguir una receta de cocina, armar un mueble o indicar cómo llegar de un lugar a otro.
</p>

<p>
En programación, diseñar buenos algoritmos es clave para construir programas claros,
eficientes y fáciles de mantener.
</p>
        """.strip()

        leccion1, _ = Leccion.objects.get_or_create(
            modulo=modulo1,
            orden=1,
            defaults={
                "titulo": "Introducción a los algoritmos",
                "contenido_html": contenido_html_1,
            },
        )

        # Lección 2: características de un buen algoritmo
        contenido_html_2 = """
<h2>Características de un buen algoritmo</h2>
<ul>
  <li><strong>Claridad:</strong> cada paso debe ser entendible.</li>
  <li><strong>Finitud:</strong> debe terminar en un número finito de pasos.</li>
  <li><strong>Definición:</strong> para la misma entrada, siempre produce la misma salida.</li>
  <li><strong>Eficiencia:</strong> usa de forma razonable tiempo y recursos.</li>
</ul>

<p>
Cuando diseñes algoritmos, pregúntate siempre si otra persona podría seguir tus pasos
sin confundirse y si el proceso está completo de principio a fin.
</p>
        """.strip()

        leccion2, _ = Leccion.objects.get_or_create(
            modulo=modulo1,
            orden=2,
            defaults={
                "titulo": "Propiedades de los algoritmos",
                "contenido_html": contenido_html_2,
            },
        )

        # Lección 3: pseudocódigo
        contenido_html_3 = """
<h2>Pseudocódigo</h2>
<p>
El pseudocódigo es una forma intermedia entre el lenguaje natural y un lenguaje
de programación. Permite describir algoritmos de manera estructurada sin preocuparse
por la sintaxis exacta de un lenguaje específico.
</p>

<pre><code>INICIO
  LEER nombre
  ESCRIBIR "Hola ", nombre
FIN</code></pre>

<p>
A partir del pseudocódigo, después podrás escribir el programa en el lenguaje
que elijas (Python, Java, etc.).
</p>
        """.strip()

        leccion3, _ = Leccion.objects.get_or_create(
            modulo=modulo2,
            orden=1,
            defaults={
                "titulo": "Pseudocódigo y representación de algoritmos",
                "contenido_html": contenido_html_3,
            },
        )

        # Lección 4: diagramas de flujo
        contenido_html_4 = """
<h2>Diagramas de flujo</h2>
<p>
Los diagramas de flujo representan visualmente los pasos de un algoritmo mediante
símbolos (óvalos, rectángulos, rombos, flechas, etc.). Son muy útiles para
comunicar y depurar procesos.
</p>

<ul>
  <li><strong>Óvalo:</strong> inicio/fin.</li>
  <li><strong>Rectángulo:</strong> proceso o instrucción.</li>
  <li><strong>Rombo:</strong> decisión (sí/no).</li>
  <li><strong>Flechas:</strong> flujo de ejecución.</li>
</ul>
        """.strip()

        leccion4, _ = Leccion.objects.get_or_create(
            modulo=modulo2,
            orden=2,
            defaults={
                "titulo": "Diagramas de flujo",
                "contenido_html": contenido_html_4,
            },
        )

        # ==========================
        # 6) Actividades
        # ==========================

        # Actividad tipo tarea (modulo1)
        actividad_tarea, _ = Actividad.objects.get_or_create(
            leccion=leccion2,
            titulo="Tarea: diseña un algoritmo de la vida diaria",
            tipo="tarea",
            defaults={
                "instrucciones": (
                    "Elige una actividad cotidiana (por ejemplo: preparar café, "
                    "organizar tu mochila, registrarse en una plataforma) y "
                    "describe el algoritmo en pasos numerados. Procura que los "
                    "pasos sean claros y finitos. Sube el archivo o escribe la "
                    "respuesta en el cuadro de texto."
                ),
                "calificacion_maxima": 10,
            },
        )

        # Actividad tipo quiz (módulo 2)
        actividad_quiz, _ = Actividad.objects.get_or_create(
            leccion=leccion3,
            titulo="Quiz: Algoritmos y lógica",
            tipo="quiz",
            defaults={
                "instrucciones": (
                    "Responde el cuestionario sobre conceptos básicos de algoritmos, "
                    "pseudocódigo y diagramas de flujo."
                ),
                "calificacion_maxima": 10,
            },
        )

        # ==========================
        # 7) Preguntas y opciones
        # ==========================
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
                OpcionPregunta(pregunta=p1, texto="Un conjunto de pasos ordenados para resolver un problema.", es_correcta=True),
                OpcionPregunta(pregunta=p1, texto="Un lenguaje de programación.", es_correcta=False),
                OpcionPregunta(pregunta=p1, texto="Un tipo de dato numérico.", es_correcta=False),
                OpcionPregunta(pregunta=p1, texto="Un archivo ejecutable.", es_correcta=False),
            ]
        )

        # Pregunta 2
        p2 = Pregunta.objects.create(
            actividad=actividad_quiz,
            texto="¿Cuál de las siguientes NO es una característica de un buen algoritmo?",
            tipo="opcion_multiple",
            orden=2,
            puntaje=1,
        )
        OpcionPregunta.objects.bulk_create(
            [
                OpcionPregunta(pregunta=p2, texto="Claridad", es_correcta=False),
                OpcionPregunta(pregunta=p2, texto="Finitud", es_correcta=False),
                OpcionPregunta(pregunta=p2, texto="Ambigüedad", es_correcta=True),
                OpcionPregunta(pregunta=p2, texto="Eficiencia", es_correcta=False),
            ]
        )

        # Pregunta 3
        p3 = Pregunta.objects.create(
            actividad=actividad_quiz,
            texto="El pseudocódigo se utiliza principalmente para:",
            tipo="opcion_multiple",
            orden=3,
            puntaje=1,
        )
        OpcionPregunta.objects.bulk_create(
            [
                OpcionPregunta(pregunta=p3, texto="Ejecutar directamente un programa.", es_correcta=False),
                OpcionPregunta(pregunta=p3, texto="Describir algoritmos de forma entendible sin sintaxis estricta.", es_correcta=True),
                OpcionPregunta(pregunta=p3, texto="Optimizar el rendimiento del procesador.", es_correcta=False),
                OpcionPregunta(pregunta=p3, texto="Diseñar interfaces gráficas.", es_correcta=False),
            ]
        )

        # Pregunta 4 (abierta)
        Pregunta.objects.create(
            actividad=actividad_quiz,
            texto="Explica con tus palabras la diferencia entre algoritmo y programa.",
            tipo="abierta",
            orden=4,
            puntaje=3,
        )

        # Pregunta 5 (abierta)
        Pregunta.objects.create(
            actividad=actividad_quiz,
            texto="Menciona un ejemplo de situación en la que usarías un diagrama de flujo para planear la solución.",
            tipo="abierta",
            orden=5,
            puntaje=4,
        )

        # ==========================
        # Listo
        # ==========================
        self.stdout.write(self.style.SUCCESS("Tercer curso demo 'Algoritmos y Lógica de Programación' creado correctamente."))
#python manage.py crear_tercer_curso_demo
