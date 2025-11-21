# lms/management/commands/crear_cursos_demo_video.py
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
    help = "Crea 4 cursos demo con 2–4 módulos, 2–4 lecciones por módulo, 1 quiz por curso y el mismo video de ejemplo."

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
            username="docente_demo_curso_1",
            defaults={
                "first_name": "Docente",
                "last_name": "Curso 1",
                "email": "docente_c1@example.com",
            },
        )
        docente2, _ = User.objects.get_or_create(
            username="docente_demo_curso_2",
            defaults={
                "first_name": "Docente",
                "last_name": "Curso 2",
                "email": "docente_c2@example.com",
            },
        )
        docente3, _ = User.objects.get_or_create(
            username="docente_demo_curso_3",
            defaults={
                "first_name": "Docente",
                "last_name": "Curso 3",
                "email": "docente_c3@example.com",
            },
        )
        docente4, _ = User.objects.get_or_create(
            username="docente_demo_curso_4",
            defaults={
                "first_name": "Docente",
                "last_name": "Curso 4",
                "email": "docente_c4@example.com",
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
                  "con_quiz": bool,  # Se usará en solo UNA lección del curso
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

            quiz_creado = False  # Para asegurar solo 1 quiz por curso

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
                                    "Lee el material de la lección y realiza una breve reflexión "
                                    "sobre cómo se aplica a tu contexto. Puedes subir un archivo "
                                    "o escribir tu respuesta en el cuadro de texto."
                                ),
                                "calificacion_maxima": 10,
                            },
                        )

                    # Actividad tipo quiz (solo 1 por curso)
                    if lex_data.get("con_quiz") and not quiz_creado:
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

                        # Idempotente: borramos preguntas previas del quiz
                        actividad_quiz.preguntas.all().delete()

                        # Pregunta demo 1
                        p1 = Pregunta.objects.create(
                            actividad=actividad_quiz,
                            texto="Esta lección incluye un video explicativo.",
                            tipo="opcion_multiple",
                            orden=1,
                            puntaje=3,
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

                        # Pregunta demo 2
                        p2 = Pregunta.objects.create(
                            actividad=actividad_quiz,
                            texto="El video y el contenido escrito se complementan para tu aprendizaje.",
                            tipo="opcion_multiple",
                            orden=2,
                            puntaje=3,
                        )
                        OpcionPregunta.objects.bulk_create(
                            [
                                OpcionPregunta(
                                    pregunta=p2,
                                    texto="De acuerdo",
                                    es_correcta=True,
                                ),
                                OpcionPregunta(
                                    pregunta=p2,
                                    texto="En desacuerdo",
                                    es_correcta=False,
                                ),
                            ]
                        )

                        # Pregunta abierta
                        Pregunta.objects.create(
                            actividad=actividad_quiz,
                            texto="Menciona un aprendizaje clave que obtuviste de este tema.",
                            tipo="abierta",
                            orden=3,
                            puntaje=4,
                        )

                        quiz_creado = True

            return curso

        # ==========================
        # Definición de los 4 cursos
        # ==========================

        # Curso 1: Inducción al Campus Virtual
        estructura_curso_1 = [
            {
                "titulo": "Bienvenida e Introducción",
                "lecciones": [
                    {
                        "titulo": "Bienvenida al Campus Virtual",
                        "contenido": """
<h2>Bienvenida al Campus Virtual</h2>
<p>
En esta lección conocerás la estructura general de la plataforma y cómo acceder a tus cursos.
</p>
""",
                        "con_video": True,
                        "con_tarea": False,
                        "con_quiz": False,
                    },
                    {
                        "titulo": "Estructura de los cursos",
                        "contenido": """
<h2>Estructura de los cursos</h2>
<p>
Exploraremos cómo se organizan los módulos, lecciones, actividades y calificaciones.
</p>
""",
                        "con_video": True,
                        "con_tarea": True,
                        "con_quiz": False,
                    },
                ],
            },
            {
                "titulo": "Uso básico de la plataforma",
                "lecciones": [
                    {
                        "titulo": "Navegación del menú principal",
                        "contenido": """
<h2>Navegación del menú principal</h2>
<p>
Identifica las secciones más importantes del menú: inicio, cursos, mensajes y perfil.
</p>
""",
                        "con_video": False,
                        "con_tarea": True,
                        "con_quiz": False,
                    },
                    {
                        "titulo": "Entrega de actividades",
                        "contenido": """
<h2>Entrega de actividades</h2>
<p>
Aprende a adjuntar archivos, redactar respuestas y verificar que tu actividad se haya enviado correctamente.
</p>
""",
                        "con_video": False,
                        "con_tarea": False,
                        "con_quiz": True,  # Único quiz de este curso
                    },
                ],
            },
        ]

        # Curso 2: Habilidades de Estudio en Línea
        estructura_curso_2 = [
            {
                "titulo": "Organización y Gestión del Tiempo",
                "lecciones": [
                    {
                        "titulo": "Planificación semanal",
                        "contenido": """
<h2>Planificación semanal</h2>
<p>
Crear un horario realista es clave para mantener el ritmo de estudio en línea.
</p>
""",
                        "con_video": True,
                        "con_tarea": True,
                        "con_quiz": False,
                    },
                    {
                        "titulo": "Evitar la procrastinación",
                        "contenido": """
<h2>Evitar la procrastinación</h2>
<p>
Conoce estrategias prácticas para mantener la concentración y avanzar en tus tareas.
</p>
""",
                        "con_video": False,
                        "con_tarea": False,
                        "con_quiz": False,
                    },
                ],
            },
            {
                "titulo": "Técnicas de Aprendizaje Activo",
                "lecciones": [
                    {
                        "titulo": "Toma de notas efectiva",
                        "contenido": """
<h2>Toma de notas efectiva</h2>
<p>
Aprende a identificar ideas clave, hacer resúmenes y mapas conceptuales.
</p>
""",
                        "con_video": True,
                        "con_tarea": True,
                        "con_quiz": False,
                    },
                    {
                        "titulo": "Autoevaluación y repaso",
                        "contenido": """
<h2>Autoevaluación y repaso</h2>
<p>
La autoevaluación continua te ayuda a fijar los conocimientos a largo plazo.
</p>
""",
                        "con_video": False,
                        "con_tarea": False,
                        "con_quiz": True,  # Único quiz de este curso
                    },
                ],
            },
        ]

        # Curso 3: Comunicación Académica
        estructura_curso_3 = [
            {
                "titulo": "Comunicación con Docentes",
                "lecciones": [
                    {
                        "titulo": "Redacción de correos formales",
                        "contenido": """
<h2>Redacción de correos formales</h2>
<p>
Incluye un saludo cordial, presenta tu contexto, explica tu duda y despídete respetuosamente.
</p>
""",
                        "con_video": True,
                        "con_tarea": True,
                        "con_quiz": False,
                    },
                    {
                        "titulo": "Tono y cortesía en la comunicación",
                        "contenido": """
<h2>Tono y cortesía</h2>
<p>
El respeto y la claridad son fundamentales al comunicarte con tus docentes.
</p>
""",
                        "con_video": False,
                        "con_tarea": False,
                        "con_quiz": False,
                    },
                ],
            },
            {
                "titulo": "Trabajo Colaborativo en Línea",
                "lecciones": [
                    {
                        "titulo": "Normas para el trabajo en equipo",
                        "contenido": """
<h2>Normas para el trabajo en equipo</h2>
<p>
Define roles, tiempos y canales de comunicación para que el trabajo colaborativo sea efectivo.
</p>
""",
                        "con_video": True,
                        "con_tarea": True,
                        "con_quiz": False,
                    },
                    {
                        "titulo": "Foros y herramientas colaborativas",
                        "contenido": """
<h2>Foros y herramientas colaborativas</h2>
<p>
Descubre cómo aprovechar foros, chats y documentos compartidos para aprender con otros.
</p>
""",
                        "con_video": False,
                        "con_tarea": False,
                        "con_quiz": True,  # Único quiz de este curso
                    },
                ],
            },
        ]

        # Curso 4: Pensamiento Lógico con Ejemplos en Python
        estructura_curso_4 = [
            {
                "titulo": "Introducción al Pensamiento Lógico",
                "lecciones": [
                    {
                        "titulo": "¿Qué es el pensamiento lógico?",
                        "contenido": """
<h2>Pensamiento lógico</h2>
<p>
Consiste en descomponer problemas en pasos ordenados y coherentes.
</p>
""",
                        "con_video": True,
                        "con_tarea": False,
                        "con_quiz": False,
                    },
                    {
                        "titulo": "Ejemplos en la vida diaria",
                        "contenido": """
<h2>Ejemplos cotidianos</h2>
<p>
Tomar decisiones, seguir instrucciones y comparar opciones son actividades que usan pensamiento lógico.
</p>
""",
                        "con_video": False,
                        "con_tarea": True,
                        "con_quiz": False,
                    },
                ],
            },
            {
                "titulo": "Algoritmos y Pseudocódigo",
                "lecciones": [
                    {
                        "titulo": "Secuencias de pasos",
                        "contenido": """
<h2>Secuencias de pasos</h2>
<p>
Antes de programar, define la solución usando lenguaje natural o pseudocódigo.
</p>
""",
                        "con_video": True,
                        "con_tarea": False,
                        "con_quiz": False,
                    },
                    {
                        "titulo": "Pensando como programador",
                        "contenido": """
<h2>Pensar como programador</h2>
<p>
Identifica entradas, procesos y salidas para diseñar soluciones más estructuradas.
</p>
""",
                        "con_video": False,
                        "con_tarea": False,
                        "con_quiz": True,  # Único quiz de este curso
                    },
                ],
            },
        ]

        # ==========================
        # Crear los cursos
        # ==========================
        crear_curso_demo(
            codigo="DEMO-INDUCCION",
            nombre="Inducción al Campus Virtual (Demo Video)",
            descripcion=(
                "Curso demo para que el estudiante se familiarice con la plataforma, "
                "módulos, lecciones, actividades y un ejemplo de video embebido."
            ),
            docente=docente1,
            estructura=estructura_curso_1,
        )

        crear_curso_demo(
            codigo="DEMO-ESTUDIO-ONLINE",
            nombre="Habilidades de Estudio en Línea (Demo Video)",
            descripcion=(
                "Curso demo sobre organización, técnicas de estudio y ejemplo de video embebido."
            ),
            docente=docente2,
            estructura=estructura_curso_2,
        )

        crear_curso_demo(
            codigo="DEMO-COMUNICACION",
            nombre="Comunicación Académica (Demo Video)",
            descripcion=(
                "Curso demo que muestra cómo debe ser la comunicación con docentes y pares, "
                "con ejemplo de video embebido."
            ),
            docente=docente3,
            estructura=estructura_curso_3,
        )

        crear_curso_demo(
            codigo="DEMO-LOGICA-PY",
            nombre="Pensamiento Lógico con Ejemplos en Python (Demo Video)",
            descripcion=(
                "Curso demo para introducir al pensamiento lógico y mostrar cómo se visualiza un video en la plataforma."
            ),
            docente=docente4,
            estructura=estructura_curso_4,
        )

        self.stdout.write(self.style.SUCCESS("Los 4 cursos demo de video se han creado / actualizado correctamente."))
