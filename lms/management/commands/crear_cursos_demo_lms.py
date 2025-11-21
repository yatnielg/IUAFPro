# lms/management/commands/crear_cursos_demo_lms.py
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model

from alumnos.models import Programa, Grupo
from lms.models import Curso, Modulo, Leccion, Actividad, Pregunta, OpcionPregunta


VIDEO_IFRAME = """
<iframe width="560" height="315"
        src="https://www.youtube.com/embed/_uQrJ0TkZlc?si=Fsl-Gx1M--khDSJe"
        title="YouTube video player"
        frameborder="0"
        allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
        referrerpolicy="strict-origin-when-cross-origin"
        allowfullscreen></iframe>
""".strip()


class Command(BaseCommand):
    help = "Crea 4 cursos demo con módulos, lecciones y el mismo video embebido en ciertas lecciones."

    def handle(self, *args, **options):
        User = get_user_model()

        # ==========================
        # 1) Programa y grupo base
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

        if not grupo:
            raise CommandError(
                "No hay Grupos creados. Crea al menos uno en alumnos.Grupo antes de ejecutar este comando."
            )

        # ==========================
        # 2) Docentes demo
        # ==========================
        docente1, _ = User.objects.get_or_create(
            username="docente_demo_1",
            defaults={
                "first_name": "Docente",
                "last_name": "Inducción",
                "email": "docente1@example.com",
            },
        )
        docente2, _ = User.objects.get_or_create(
            username="docente_demo_2",
            defaults={
                "first_name": "Docente",
                "last_name": "Estudio en Línea",
                "email": "docente2@example.com",
            },
        )
        docente3, _ = User.objects.get_or_create(
            username="docente_demo_3",
            defaults={
                "first_name": "Docente",
                "last_name": "Comunicación",
                "email": "docente3@example.com",
            },
        )
        docente4, _ = User.objects.get_or_create(
            username="docente_demo_4",
            defaults={
                "first_name": "Docente",
                "last_name": "Pensamiento Lógico",
                "email": "docente4@example.com",
            },
        )

        # Helper para crear curso con módulos / lecciones / actividades
        def crear_curso_demo(codigo, nombre, descripcion, docente, estructura):
            """
            estructura = lista de módulos, cada uno:
            {
              "titulo": str,
              "lecciones": [
                {
                  "titulo": str,
                  "contenido": str,
                  "con_video": bool,
                  "con_tarea": bool,
                  "con_quiz": bool,
                },
                ...
              ]
            }
            """
            curso, creado = Curso.objects.get_or_create(
                codigo=codigo,
                defaults={
                    "programa": programa,
                    "grupo": grupo,
                    "nombre": nombre,
                    "descripcion": descripcion,
                    "docente": docente,
                    "activo": True,
                },
            )

            if creado:
                self.stdout.write(self.style.SUCCESS(f"Curso {codigo} creado."))
            else:
                self.stdout.write(self.style.WARNING(f"Curso {codigo} ya existía, se reutiliza."))

            for i_mod, mod_data in enumerate(estructura, start=1):
                modulo, _ = Modulo.objects.get_or_create(
                    curso=curso,
                    orden=i_mod,
                    defaults={
                        "titulo": mod_data["titulo"],
                    },
                )

                for i_lex, lex_data in enumerate(mod_data["lecciones"], start=1):
                    contenido = lex_data.get("contenido", "").strip()

                    # Si la lección lleva video, lo agregamos al contenido_html
                    if lex_data.get("con_video"):
                        contenido = f"{contenido}\n\n{VIDEO_IFRAME}"

                    leccion, _ = Leccion.objects.get_or_create(
                        modulo=modulo,
                        orden=i_lex,
                        defaults={
                            "titulo": lex_data["titulo"],
                            "contenido_html": contenido,
                            # url_video lo podemos dejar vacío, usamos iframe en contenido_html
                        },
                    )

                    # Actividad tipo tarea
                    if lex_data.get("con_tarea"):
                        Actividad.objects.get_or_create(
                            leccion=leccion,
                            tipo="tarea",
                            titulo=f"Tarea: {lex_data['titulo']}",
                            defaults={
                                "instrucciones": (
                                    "Lee el material de la lección y realiza una reflexión breve "
                                    "sobre cómo se aplica a tu contexto. Puedes subir un archivo "
                                    "o escribir tu respuesta en el cuadro de texto."
                                ),
                                "calificacion_maxima": 10,
                            },
                        )

                    # Actividad tipo quiz (demo simple)
                    if lex_data.get("con_quiz"):
                        actividad_quiz, _ = Actividad.objects.get_or_create(
                            leccion=leccion,
                            tipo="quiz",
                            titulo=f"Quiz: {lex_data['titulo']}",
                            defaults={
                                "instrucciones": (
                                    "Responde las preguntas de opción múltiple sobre los conceptos "
                                    "revisados en esta lección."
                                ),
                                "calificacion_maxima": 10,
                            },
                        )

                        # Para que sea idempotente, borramos preguntas previas del quiz
                        actividad_quiz.preguntas.all().delete()

                        # Pregunta demo 1
                        p1 = Pregunta.objects.create(
                            actividad=actividad_quiz,
                            texto="Esta lección incluye un video explicativo.",
                            tipo="opcion_multiple",
                            orden=1,
                            puntaje=1,
                        )
                        OpcionPregunta.objects.bulk_create(
                            [
                                OpcionPregunta(
                                    pregunta=p1,
                                    texto="Verdadero",
                                    es_correcta=True,
                                ),
                                OpcionPregunta(
                                    pregunta=p1,
                                    texto="Falso",
                                    es_correcta=False,
                                ),
                            ]
                        )

                        # Pregunta demo abierta
                        Pregunta.objects.create(
                            actividad=actividad_quiz,
                            texto="Escribe un aprendizaje clave que te llevas de esta lección.",
                            tipo="abierta",
                            orden=2,
                            puntaje=4,
                        )

            return curso

        # ==========================
        # Definición de los 4 cursos
        # ==========================

        # 1) Inducción al Campus Virtual
        estructura_curso_1 = [
            {
                "titulo": "Bienvenida e introducción",
                "lecciones": [
                    {
                        "titulo": "Conoce el campus virtual",
                        "contenido": """
<h2>Bienvenida al Campus Virtual</h2>
<p>
En esta lección conocerás la estructura general de la plataforma, cómo ingresar
a tus cursos, revisar contenidos, entregar actividades y revisar tus calificaciones.
</p>
""",
                        "con_video": True,
                        "con_tarea": False,
                        "con_quiz": False,
                    },
                    {
                        "titulo": "Navegación básica",
                        "contenido": """
<h2>Navegación básica</h2>
<p>
Asegúrate de identificar el menú principal, la sección de cursos y el panel de notificaciones.
</p>
""",
                        "con_video": False,
                        "con_tarea": True,
                        "con_quiz": False,
                    },
                ],
            },
            {
                "titulo": "Soporte y comunicación",
                "lecciones": [
                    {
                        "titulo": "Canales de soporte",
                        "contenido": """
<h2>Canales de soporte</h2>
<p>
En caso de dudas técnicas, académicas o administrativas, puedes comunicarte por los
canales establecidos por la institución (correo, WhatsApp, mesa de ayuda, etc.).
</p>
""",
                        "con_video": False,
                        "con_tarea": False,
                        "con_quiz": True,
                    },
                ],
            },
        ]

        # 2) Habilidades de Estudio en Línea
        estructura_curso_2 = [
            {
                "titulo": "Organización del tiempo",
                "lecciones": [
                    {
                        "titulo": "Planificación de tu semana",
                        "contenido": """
<h2>Planificación de tu semana</h2>
<p>
Estudiar en línea requiere disciplina. Diseña un horario realista considerando tus otras actividades.
</p>
""",
                        "con_video": True,
                        "con_tarea": True,
                        "con_quiz": False,
                    },
                ],
            },
            {
                "titulo": "Estrategias de aprendizaje",
                "lecciones": [
                    {
                        "titulo": "Técnicas de estudio activo",
                        "contenido": """
<h2>Técnicas de estudio activo</h2>
<ul>
  <li>Tomar notas durante el video.</li>
  <li>Hacer resúmenes después de cada lección.</li>
  <li>Plantear preguntas y autoevaluarte.</li>
</ul>
""",
                        "con_video": False,
                        "con_tarea": False,
                        "con_quiz": True,
                    },
                ],
            },
        ]

        # 3) Comunicación Académica
        estructura_curso_3 = [
            {
                "titulo": "Comunicación con docentes",
                "lecciones": [
                    {
                        "titulo": "Buenas prácticas al escribir correos",
                        "contenido": """
<h2>Correos académicos efectivos</h2>
<p>
Utiliza un asunto claro, preséntate, explica tu duda con contexto y cierra con una despedida cordial.
</p>
""",
                        "con_video": True,
                        "con_tarea": True,
                        "con_quiz": False,
                    },
                ],
            },
            {
                "titulo": "Trabajo en equipo en línea",
                "lecciones": [
                    {
                        "titulo": "Etiquetas para trabajo colaborativo",
                        "contenido": """
<h2>Trabajo colaborativo</h2>
<p>
Respeta los tiempos de tus compañeros, acuerda reglas claras y utiliza los foros y herramientas
colaborativas de la plataforma.
</p>
""",
                        "con_video": False,
                        "con_tarea": False,
                        "con_quiz": True,
                    },
                ],
            },
        ]

        # 4) Pensamiento lógico con ejemplos en Python (demo general)
        estructura_curso_4 = [
            {
                "titulo": "Introducción al pensamiento lógico",
                "lecciones": [
                    {
                        "titulo": "Qué es pensar lógicamente",
                        "contenido": """
<h2>Pensamiento lógico</h2>
<p>
El pensamiento lógico te ayuda a descomponer problemas en pasos pequeños y ordenados.
Es la base para la programación y la resolución de problemas complejos.
</p>
""",
                        "con_video": True,
                        "con_tarea": False,
                        "con_quiz": False,
                    },
                    {
                        "titulo": "Ejemplos cotidianos",
                        "contenido": """
<h2>Ejemplos de la vida diaria</h2>
<p>
Tomar decisiones, comparar opciones y seguir instrucciones son actividades que usan pensamiento lógico.
</p>
""",
                        "con_video": False,
                        "con_tarea": True,
                        "con_quiz": False,
                    },
                ],
            },
            {
                "titulo": "Primeros pasos con algoritmos",
                "lecciones": [
                    {
                        "titulo": "Pasos secuenciales",
                        "contenido": """
<h2>Secuencias de pasos</h2>
<p>
Antes de programar, define la secuencia de pasos usando lenguaje natural o pseudocódigo.
</p>
""",
                        "con_video": False,
                        "con_tarea": False,
                        "con_quiz": True,
                    },
                ],
            },
        ]

        # ==========================
        # Crear los cursos
        # ==========================
        crear_curso_demo(
            codigo="CAMPUS-IND",
            nombre="Inducción al Campus Virtual (Demo)",
            descripcion=(
                "Curso demo para que el estudiante se familiarice con la plataforma, "
                "los canales de apoyo y la forma de trabajo en línea."
            ),
            docente=docente1,
            estructura=estructura_curso_1,
        )

        crear_curso_demo(
            codigo="ONLINE-HAB",
            nombre="Habilidades de Estudio en Línea (Demo)",
            descripcion=(
                "Curso demo sobre hábitos, organización del tiempo y estrategias para "
                "aprovechar mejor el estudio en modalidad virtual."
            ),
            docente=docente2,
            estructura=estructura_curso_2,
        )

        crear_curso_demo(
            codigo="COM-ACA",
            nombre="Comunicación Académica (Demo)",
            descripcion=(
                "Curso demo que aborda la comunicación adecuada con docentes y pares, "
                "así como el trabajo colaborativo en entornos virtuales."
            ),
            docente=docente3,
            estructura=estructura_curso_3,
        )

        crear_curso_demo(
            codigo="LOGIC-PY",
            nombre="Pensamiento Lógico con Ejemplos en Python (Demo)",
            descripcion=(
                "Curso demo para introducir al estudiante al pensamiento lógico y a los "
                "primeros pasos en el diseño de algoritmos."
            ),
            docente=docente4,
            estructura=estructura_curso_4,
        )

        self.stdout.write(self.style.SUCCESS("Los 4 cursos demo se han creado / actualizado correctamente."))
