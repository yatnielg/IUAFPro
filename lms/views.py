# lms/views.py
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.contrib import messages

from alumnos.models import Alumno
from .models import Curso, Actividad, Entrega, AccesoCurso, IntentoQuiz
from .forms import EntregaForm

from django.http import HttpResponseForbidden

from django.db.models import Count, Q
import random

from django.contrib.admin.views.decorators import staff_member_required

def _get_alumno_from_user(user):
    """
    Intenta obtener el Alumno vinculado al usuario.
    """
    if not user.is_authenticated:
        return None

    return (
        Alumno.objects
        .select_related(
            "informacionEscolar",
            "informacionEscolar__grupo_nuevo",   # 👈 AQUÍ el grupo FK real
        )
        .filter(user=user)
        .first()
    )


from django.db.models import Count, Q, Case, When, IntegerField
from django.utils import timezone
import random

@login_required
def mis_cursos(request):
    alumno = _get_alumno_from_user(request.user)
    cursos = Curso.objects.filter(activo=True)
    alumno_random = random.randint(326, 645)  # (ahora mismo no se usa)

    info = getattr(alumno, "informacionEscolar", None) if alumno else None

    # Filtrar por grupo_nuevo (FK a Grupo) y opcionalmente por programa
    if info and info.grupo_nuevo_id:
        cursos = cursos.filter(
            programa=info.programa,
            grupo=info.grupo_nuevo,
        )
    else:
        if info and info.programa_id:
            cursos = cursos.filter(programa=info.programa)
        else:
            cursos = Curso.objects.none()

    # Fecha de hoy (para lógica de terminado / disponible)
    hoy = timezone.now().date()

    # Anotar contadores
    cursos = cursos.annotate(
        total_lecciones=Count("modulos__lecciones", distinct=True),
        total_quizzes=Count(
            "modulos__lecciones__actividades",
            filter=Q(modulos__lecciones__actividades__tipo="quiz"),
            distinct=True,
        ),
        total_estudiantes=Count("accesos__alumno", distinct=True) + 355,  # demo
    )

    # 👇 Marcar cursos terminados y ordenar: primero activos / en curso / futuros,
    # luego los finalizados
    cursos = cursos.annotate(
        terminado=Case(
            When(fecha_fin__lt=hoy, then=1),
            default=0,
            output_field=IntegerField(),
        )
    ).order_by("terminado", "fecha_inicio", "nombre")

    # Calcular si el curso está disponible según fechas
    for c in cursos:
        disponible = True

        if c.fecha_inicio and c.fecha_inicio > hoy:
            disponible = False
        if c.fecha_fin and c.fecha_fin < hoy:
            disponible = False

        c.disponible = disponible

        # días para que inicie (solo si aún no inicia)
        if c.fecha_inicio and c.fecha_inicio > hoy:
            c.dias_para_inicio = (c.fecha_inicio - hoy).days
        else:
            c.dias_para_inicio = None

    context = {
        "alumno": alumno,
        "cursos": cursos,
        "hoy": hoy,
    }
    return render(request, "lms/mis_cursos.html", context)

############################################################################


@login_required
def curso_detalle(request, pk):
    alumno = _get_alumno_from_user(request.user)
    curso = get_object_or_404(
        Curso.objects.prefetch_related("modulos__lecciones__actividades"),
        pk=pk,
        activo=True,
    )

    info = getattr(alumno, "informacionEscolar", None) if alumno else None

    # Seguridad alumno (como ya lo tenías)
    if info and info.grupo_nuevo and curso.grupo and curso.grupo != info.grupo_nuevo:
        messages.error(request, "No tienes acceso a este curso.")
        return redirect("lms:mis_cursos")

    # Registrar acceso del alumno (opcional)
    if alumno:
        AccesoCurso.objects.update_or_create(
            alumno=alumno,
            curso=curso,
            defaults={"ultimo_acceso": timezone.now()},
        )

    # 👇 Aquí definimos si este usuario es docente de ese curso o staff
    user = request.user
    es_docente = bool(
        user.is_staff or user.is_superuser or curso.docente_id == user.id
    )

    context = {
        "alumno": alumno,
        "curso": curso,
        "modulos": curso.modulos.all(),
        "es_docente": es_docente,   # 👈 clave para el template
    }
    return render(request, "lms/curso_detalle.html", context)
############################################################################
from django.db import transaction
from .models import Curso, Actividad, Entrega, AccesoCurso, IntentoQuiz, RespuestaPregunta, Pregunta
from .forms import EntregaForm, QuizForm

@login_required
def actividad_detalle(request, pk):
    alumno = _get_alumno_from_user(request.user)
    actividad = get_object_or_404(
        Actividad.objects.select_related("leccion__modulo__curso"),
        pk=pk,
    )
    curso = actividad.leccion.modulo.curso

    # seguridad: validar acceso al curso (grupo oficial)
    info = getattr(alumno, "informacionEscolar", None) if alumno else None
    if info and info.grupo_nuevo and curso.grupo and curso.grupo != info.grupo_nuevo:
        messages.error(request, "No tienes acceso a esta actividad.")
        return redirect("lms:mis_cursos")

    # === CASO 1: NO ES QUIZ (tarea normal) ============================
    if actividad.tipo != "quiz":
        entrega = None
        if alumno:
            entrega = Entrega.objects.filter(actividad=actividad, alumno=alumno).first()

        if request.method == "POST":
            form = EntregaForm(request.POST, request.FILES, instance=entrega)
            if form.is_valid():
                entrega = form.save(commit=False)
                entrega.actividad = actividad
                entrega.alumno = alumno
                entrega.enviado_en = timezone.now()
                entrega.save()
                messages.success(request, "Tu entrega se guardó correctamente.")
                return redirect("lms:actividad_detalle", pk=actividad.pk)
        else:
            form = EntregaForm(instance=entrega)

        context = {
            "alumno": alumno,
            "curso": curso,
            "actividad": actividad,
            "entrega": entrega,
            "form": form,
            "es_quiz": False,
        }
        return render(request, "lms/actividad_detalle.html", context)

    # === CASO 2: ES QUIZ ===============================================
    # Obtener o crear intento
    intento = None
    if alumno:
        intento, _ = IntentoQuiz.objects.get_or_create(
            actividad=actividad,
            alumno=alumno,
        )

    if request.method == "POST":
        form = QuizForm(request.POST, actividad=actividad)
        if form.is_valid() and intento:
            with transaction.atomic():
                # Borrar respuestas previas (si quieres permitir reintento)
                intento.respuestas.all().delete()

                total_obtenido = 0
                total_posible = 0

                for pregunta in actividad.preguntas.all():
                    field_name = f"pregunta_{pregunta.id}"
                    valor = form.cleaned_data.get(field_name)

                    # Guardar respuesta
                    resp = RespuestaPregunta(
                        intento=intento,
                        pregunta=pregunta,
                    )

                    if pregunta.tipo == "opcion_multiple":
                        opcion = pregunta.opciones.filter(id=valor).first()
                        resp.opcion = opcion
                        resp.texto_respuesta = opcion.texto if opcion else ""
                        # Calificar
                        if opcion and opcion.es_correcta:
                            total_obtenido += float(pregunta.puntaje)
                        total_posible += float(pregunta.puntaje)
                    else:
                        # abierta
                        resp.texto_respuesta = valor
                        # Por ahora, abiertas NO suman auto; lo puedes ajustar o revisar manual
                        total_posible += float(pregunta.puntaje)

                    resp.save()

                # Calificación sobre 10 (escala)
                if total_posible > 0:
                    score = (total_obtenido / total_posible) * float(actividad.calificacion_maxima)
                else:
                    score = 0

                intento.calificacion_obtenida = score
                intento.completado_en = timezone.now()
                intento.save()

            messages.success(request, f"Respuestas guardadas. Calificación: {score:.2f}")
            return redirect("lms:actividad_detalle", pk=actividad.pk)
    else:
        form = QuizForm(actividad=actividad)

    context = {
        "alumno": alumno,
        "curso": curso,
        "actividad": actividad,
        "form": form,
        "intento": intento,
        "es_quiz": True,
    }
    return render(request, "lms/actividad_detalle.html", context)



################################################################################
@login_required
def actividad_respuestas(request, pk):
    """
    Vista para DOCENTE / STAFF: ver respuestas de una actividad (tarea o quiz).
    """
    actividad = get_object_or_404(
        Actividad.objects.select_related("leccion__modulo__curso"),
        pk=pk,
    )
    curso = actividad.leccion.modulo.curso

    # --- Permisos básicos: docente del curso o staff/superuser ---
    user = request.user
    if not (user.is_staff or user.is_superuser or curso.docente_id == user.id):
        return HttpResponseForbidden("No tienes permiso para ver estas respuestas.")

    contexto_base = {
        "curso": curso,
        "actividad": actividad,
        "es_docente": True,
    }

    # ---------- TAREA NORMAL ----------
    if actividad.tipo != "quiz":
        entregas = (
            Entrega.objects
            .filter(actividad=actividad)
            .select_related("alumno")
            .order_by("-enviado_en")
        )
        contexto_base["entregas"] = entregas
        return render(request, "lms/actividad_respuestas.html", contexto_base)

    # ---------- QUIZ ----------
    # Prefetch de respuestas + pregunta + opción
    intentos = (
        IntentoQuiz.objects
        .filter(actividad=actividad)
        .select_related("alumno")
        .prefetch_related("respuestas__pregunta", "respuestas__opcion")
        .order_by("-completado_en", "-iniciado_en")
    )

    contexto_base["intentos"] = intentos
    return render(request, "lms/actividad_respuestas.html", contexto_base)

##############################################################################
@staff_member_required  # Solo superusuarios o staff
def cursos_todos(request):
    """
    Lista TODOS los cursos para administración global.
    """
    q = request.GET.get("q", "").strip()

    cursos = (
        Curso.objects
        .select_related("programa", "grupo", "docente")
        .prefetch_related("modulos__lecciones__actividades")
        .annotate(
            num_alumnos=Count("accesos", distinct=True),
            num_modulos=Count("modulos", distinct=True),
            num_lecciones=Count("modulos__lecciones", distinct=True),
            num_quizzes=Count(
                "modulos__lecciones__actividades",
                filter=Q(modulos__lecciones__actividades__tipo="quiz"),
                distinct=True,
            ),
        )
        .order_by("programa__codigo", "nombre")
    )

    if q:
        cursos = cursos.filter(
            Q(codigo__icontains=q) |
            Q(nombre__icontains=q) |
            Q(docente__first_name__icontains=q) |
            Q(docente__last_name__icontains=q)
        )

    context = {
        "cursos": cursos,
        "q": q,
        "es_docente": True,  # para reusar templates que revisan esto
    }
    return render(request, "lms/cursos_todos.html", context)