# lms/management/commands/crear_cuarto_curso_demo.py
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
    help = (
        "Crea un cuarto curso demo (Estructuras de Datos con Python) "
        "con módulos, lecciones y quiz."
    )

    def handle(self, *args, **options):
        User = get_user_model()

        # ==========================
        # 1) Buscar programa y grupo
        # ==========================
        programa = Programa.objects.order_by("id").first()
        if not programa:
            raise CommandError(
                "No hay Programas creados. Crea al menos uno en alumnos.Programa "
                "antes de ejecutar este comando."
            )

        grupo = (
            Grupo.objects.filter(programa=programa).order_by("id").first()
            or Grupo.objects.order_by("id").first()
        )

        # ==========================
        # 2) Docente demo
        # ==========================
        docente, _ = User.objects.get_or_create(
            username="docente_demo_estructuras",
            defaults={
                "first_name": "Docente",
                "last_name": "Estructuras",
                "email": "docente.estructuras@example.com",
            },
        )

        # ==========================
        # 3) Curso
        # ==========================
        curso, creado = Curso.objects.get_or_create(
            codigo="ED-PY-DEM",
            defaults={
                "programa": programa,
                "grupo": grupo,
                "nombre": "Estructuras de Datos con Python (Demo)",
                "descripcion": (
                    "Curso demo de estructuras de datos con Python. "
                    "Introduce listas, tuplas, diccionarios y conjuntos, "
                    "así como su uso en problemas cotidianos."
                ),
                "docente": docente,
                "activo": True,
            },
        )

        if not creado:
            self.stdout.write(
                self.style.WARNING("El curso ED-PY-DEM ya existía, se reutilizará.")
            )

        # ==========================
        # 4) Módulos
        # ==========================
        modulo1, _ = Modulo.objects.get_or_create(
            curso=curso,
            orden=1,
            defaults={"titulo": "Módulo 1: Colecciones básicas en Python"},
        )
        modulo2, _ = Modulo.objects.get_or_create(
            curso=curso,
            orden=2,
            defaults={"titulo": "Módulo 2: Trabajo práctico con estructuras de datos"},
        )

        # ==========================
        # 5) Lecciones
        # ==========================

        # Lección 1: listas y tuplas
        contenido_html_1 = """
<h2>Listas y tuplas en Python</h2>
<p>
Las listas y las tuplas son estructuras que permiten almacenar colecciones
de elementos. La diferencia principal es que las listas son mutables y
las tuplas inmutables.
</p>

<pre><code># Lista
numeros = [1, 2, 3]
numeros.append(4)

# Tupla
coordenadas = (10, 20)</code></pre>

<p>
Las listas se usan cuando necesitas agregar, eliminar o modificar elementos.
Las tuplas son útiles para datos que no deben cambiar.
</p>
        """.strip()

        leccion1, _ = Leccion.objects.get_or_create(
            modulo=modulo1,
            orden=1,
            defaults={
                "titulo": "Listas y tuplas",
                "contenido_html": contenido_html_1,
            },
        )

        # Lección 2: diccionarios y conjuntos
        contenido_html_2 = """
<h2>Diccionarios y conjuntos</h2>
<p>
Los diccionarios permiten almacenar pares clave-valor, mientras que los
conjuntos almacenan elementos únicos, sin orden y sin repetidos.
</p>

<pre><code># Diccionario
persona = {
    "nombre": "Ana",
    "edad": 25,
    "ciudad": "Bogotá",
}

# Conjunto
colores = {"rojo", "verde", "azul"}</code></pre>

<p>
Estas estructuras son muy útiles para búsquedas rápidas y para eliminar
duplicados en colecciones.
</p>
        """.strip()

        leccion2, _ = Leccion.objects.get_or_create(
            modulo=modulo1,
            orden=2,
            defaults={
                "titulo": "Diccionarios y conjuntos",
                "contenido_html": contenido_html_2,
            },
        )

        # Lección 3: orientada al quiz
        contenido_html_3 = """
<h2>Quiz: estructuras de datos</h2>
<p>
Responde el cuestionario para comprobar tu comprensión sobre listas, tuplas,
diccionarios y conjuntos en Python.
</p>
        """.strip()

        leccion3, _ = Leccion.objects.get_or_create(
            modulo=modulo2,
            orden=1,
            defaults={
                "titulo": "Quiz: Estructuras de datos en Python",
                "contenido_html": contenido_html_3,
            },
        )

        # Lección 4: mini proyecto
        contenido_html_4 = """
<h2>Mini proyecto: agenda de contactos</h2>
<p>
Como ejercicio integrador, construirás una pequeña agenda de contactos en Python
usando diccionarios y listas. Podrás agregar, buscar y listar contactos.
</p>
        """.strip()

        leccion4, _ = Leccion.objects.get_or_create(
            modulo=modulo2,
            orden=2,
            defaults={
                "titulo": "Mini proyecto con estructuras de datos",
                "contenido_html": contenido_html_4,
            },
        )

        # ==========================
        # 6) Actividades
        # ==========================

        # Actividad tipo tarea (mini proyecto)
        actividad_tarea, _ = Actividad.objects.get_or_create(
            leccion=leccion4,
            titulo="Tarea: agenda de contactos en Python",
            tipo="tarea",
            defaults={
                "instrucciones": (
                    "Crea un programa en Python que permita: "
                    "1) agregar contactos (nombre, teléfono), "
                    "2) buscar un contacto por nombre y "
                    "3) listar todos los contactos. "
                    "Usa listas y diccionarios. Sube el archivo .py o pega el código."
                ),
                "calificacion_maxima": 10,
            },
        )

        # Actividad tipo quiz
        actividad_quiz, _ = Actividad.objects.get_or_create(
            leccion=leccion3,
            titulo="Quiz: colecciones en Python",
            tipo="quiz",
            defaults={
                "instrucciones": (
                    "Responde las preguntas sobre listas, tuplas, diccionarios "
                    "y conjuntos en Python. Algunas preguntas son de opción múltiple "
                    "y otras abiertas."
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
            texto="¿Qué estructura de datos de Python es mutable?",
            tipo="opcion_multiple",
            orden=1,
            puntaje=1,
        )
        OpcionPregunta.objects.bulk_create(
            [
                OpcionPregunta(pregunta=p1, texto="Tupla", es_correcta=False),
                OpcionPregunta(pregunta=p1, texto="Lista", es_correcta=True),
                OpcionPregunta(pregunta=p1, texto="Cadena (str)", es_correcta=False),
                OpcionPregunta(pregunta=p1, texto="Ninguna de las anteriores", es_correcta=False),
            ]
        )

        # Pregunta 2
        p2 = Pregunta.objects.create(
            actividad=actividad_quiz,
            texto="¿Qué estructura de datos usarías para almacenar pares clave-valor?",
            tipo="opcion_multiple",
            orden=2,
            puntaje=1,
        )
        OpcionPregunta.objects.bulk_create(
            [
                OpcionPregunta(pregunta=p2, texto="Lista", es_correcta=False),
                OpcionPregunta(pregunta=p2, texto="Conjunto", es_correcta=False),
                OpcionPregunta(pregunta=p2, texto="Diccionario", es_correcta=True),
                OpcionPregunta(pregunta=p2, texto="Tupla", es_correcta=False),
            ]
        )

        # Pregunta 3
        p3 = Pregunta.objects.create(
            actividad=actividad_quiz,
            texto="¿Qué ventaja principal tiene un conjunto (set) en Python?",
            tipo="opcion_multiple",
            orden=3,
            puntaje=1,
        )
        OpcionPregunta.objects.bulk_create(
            [
                OpcionPregunta(pregunta=p3, texto="Permite índices negativos.", es_correcta=False),
                OpcionPregunta(pregunta=p3, texto="Almacena elementos únicos sin duplicados.", es_correcta=True),
                OpcionPregunta(pregunta=p3, texto="Es siempre ordenado.", es_correcta=False),
                OpcionPregunta(pregunta=p3, texto="Solo admite números enteros.", es_correcta=False),
            ]
        )

        # Pregunta 4 (abierta)
        Pregunta.objects.create(
            actividad=actividad_quiz,
            texto="Explica con tus palabras la diferencia entre una lista y una tupla en Python.",
            tipo="abierta",
            orden=4,
            puntaje=3,
        )

        # Pregunta 5 (abierta)
        Pregunta.objects.create(
            actividad=actividad_quiz,
            texto="Describe una situación real donde usarías un diccionario para organizar información.",
            tipo="abierta",
            orden=5,
            puntaje=4,
        )

        # ==========================
        # Listo
        # ==========================
        self.stdout.write(
            self.style.SUCCESS(
                "Cuarto curso demo 'Estructuras de Datos con Python' creado correctamente."
            )
        )
