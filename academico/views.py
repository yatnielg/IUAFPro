# academico/views.py
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.db.models import Count, Min, Max, Case, When, Value, CharField

from alumnos.models import Programa
from .models import (
    ListadoMaterias,
    ListadoMateriaItem,
    ListadoAlumno,
    Calificacion,
)
from .forms import CalificacionForm, CalificacionFormSet


# ---------- Listado con métricas y estado ----------
@login_required
def listados_list(request):
    """
    Listado de 'Listados de materias' con métricas y estado calculado.
    Filtros básicos por GET (opcional) y filtros ricos en cliente con DataTables.
    """
    hoy = timezone.localdate()

    # ---- Permisos: superuser o grupo 'editar_estatus_academico'
    puede_ver = (
        request.user.is_superuser
        or request.user.groups.filter(name="editar_estatus_academico").exists()
    )

    if not puede_ver:
        # Opcional: messages.info(request, "No tienes permisos para ver estos listados.")
        return render(
            request,
            "academico/listados_list.html",
            {
                "listados": ListadoMaterias.objects.none(),
                "programas": Programa.objects.none(),
                "prog_code": (request.GET.get("programa") or "").strip(),
                "q": (request.GET.get("q") or "").strip(),
            },
        )


    qs = (
        ListadoMaterias.objects
        .select_related("programa")
        .annotate(
            items_count=Count("items", distinct=True),
            inscritos_count=Count("inscripciones", distinct=True),
            inicio=Min("items__fecha_inicio"),
            fin=Max("items__fecha_fin"),
        )
        .annotate(
            estado=Case(
                When(inicio__isnull=True, fin__isnull=True, then=Value("Sin fechas")),
                When(fin__lt=hoy, then=Value("Finalizado")),
                When(inicio__gt=hoy, then=Value("Próximo")),
                default=Value("Vigente"),
                output_field=CharField(),
            )
        )
        .order_by("-creado_en")
    )

    prog_code = (request.GET.get("programa") or "").strip()
    if prog_code:
        qs = qs.filter(programa__codigo__iexact=prog_code)

    q = (request.GET.get("q") or "").strip()
    if q:
        qs = qs.filter(nombre__icontains=q)

    programas = Programa.objects.all().order_by("codigo")

    return render(
        request,
        "academico/listados_list.html",
        {
            "listados": qs,
            "programas": programas,
            "prog_code": prog_code,
            "q": q,
        },
    )


# ---------- Detalle de un listado ----------
@login_required
def listado_detalle(request, pk):
    """
    Detalle de un Listado: info general, materias (items) y alumnos inscritos.
    """
    listado = get_object_or_404(
        ListadoMaterias.objects.select_related("programa"),
        pk=pk,
    )

    items = (
        ListadoMateriaItem.objects
        .filter(listado=listado)
        .select_related("materia")
        .order_by("fecha_inicio", "materia__codigo")
    )

    inscripciones = (
        ListadoAlumno.objects
        .filter(listado=listado)
        .select_related("alumno", "alumno__informacionEscolar")
        .order_by("alumno__numero_estudiante")
    )

    calif_por_item = {
        it.id: Calificacion.objects.filter(item=it).count()
        for it in items
    }

    return render(
        request,
        "academico/listado_detalle.html",
        {
            "listado": listado,
            "items": items,
            "inscripciones": inscripciones,
            "calif_por_item": calif_por_item,
        },
    )


# ---------- Editor masivo de calificaciones por Item ----------
@login_required
@transaction.atomic
def calificaciones_item(request, pk):
    """
    Editor tipo 'admin inline' para las calificaciones de un ListadoMateriaItem.
    Trae a los alumnos inscritos en el listado del item; asegura una calificación por alumno.
    """
    item = get_object_or_404(
        ListadoMateriaItem.objects.select_related(
            "listado", "listado__programa", "materia"
        ),
        pk=pk,
    )

    # Alumnos inscritos al listado del item (ordenados)
    inscripciones = (
        ListadoAlumno.objects
        .filter(listado=item.listado)
        .select_related("alumno")
        .order_by("alumno__numero_estudiante")
    )
    alumnos_ids = [ins.alumno_id for ins in inscripciones]

    # 1) Limpieza defensiva: borra calificaciones sin alumno para este item
    Calificacion.objects.filter(item=item, alumno__isnull=True).delete()

    # 2) Asegura que exista 1 calificación por alumno-inscrito (idempotente)
    for aid in alumnos_ids:
        Calificacion.objects.get_or_create(
            item=item,
            alumno_id=aid,
            defaults={"nota": None},
        )

    # Query base para el formset
    qs_califs = (
        Calificacion.objects
        .filter(item=item, alumno_id__in=alumnos_ids, alumno__isnull=False)
        .select_related("alumno")
        .order_by("alumno__numero_estudiante")
    )

    if request.method == "POST":
        formset = CalificacionFormSet(request.POST, queryset=qs_califs)
        if formset.is_valid():
            objs = formset.save(commit=False)
            # Guardado robusto: asegura item y revalida cada instancia
            for obj in objs:
                obj.item = item
                obj.full_clean()  # invoca model.clean si lo tienes
                obj.save()
            messages.success(request, "Calificaciones guardadas.")
            return redirect("academico:calificaciones_item", pk=item.pk)
        messages.error(request, "Revisa los errores en el formulario.")
    else:
        formset = CalificacionFormSet(queryset=qs_califs)

    return render(
        request,
        "academico/calificaciones_item.html",
        {
            "item": item,
            "listado": item.listado,
            "formset": formset,
            "inscripciones": inscripciones,
        },
    )
