# academico/views.py
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.forms import modelformset_factory
from django.shortcuts import get_object_or_404, redirect, render

from alumnos.models import Alumno, Programa
from .models import ListadoMaterias, ListadoMateriaItem, ListadoAlumno, Calificacion


@login_required
def listados_list(request):
    """
    Lista de listados con filtros básicos: por programa (código) y búsqueda por nombre.
    """
    qs = ListadoMaterias.objects.select_related("programa").order_by("-creado_en")

    prog_code = request.GET.get("programa", "").strip()
    if prog_code:
        qs = qs.filter(programa__codigo__iexact=prog_code)

    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(nombre__icontains=q)

    # Para combo de programas
    programas = Programa.objects.all().order_by("codigo")

    return render(request, "academico/listados_list.html", {
        "listados": qs,
        "programas": programas,
        "prog_code": prog_code,
        "q": q,
    })


@login_required
def listado_detalle(request, pk):
    """
    Detalle de un Listado: info general, materias (items) y alumnos inscritos.
    """
    listado = get_object_or_404(
        ListadoMaterias.objects.select_related("programa"),
        pk=pk
    )

    items = (ListadoMateriaItem.objects
             .filter(listado=listado)
             .select_related("materia")
             .order_by("fecha_inicio", "materia__codigo"))

    inscripciones = (ListadoAlumno.objects
                     .filter(listado=listado)
                     .select_related("alumno", "alumno__informacionEscolar")
                     .order_by("alumno__numero_estudiante"))

    # Para mostrar conteos de calificaciones por cada item
    calif_por_item = {
        it.id: Calificacion.objects.filter(item=it).count() for it in items
    }

    return render(request, "academico/listado_detalle.html", {
        "listado": listado,
        "items": items,
        "inscripciones": inscripciones,
        "calif_por_item": calif_por_item,
    })


@login_required
@transaction.atomic
def calificaciones_item(request, pk):
    """
    Editor tipo 'admin inline' para las calificaciones de un ListadoMateriaItem.
    Trae a los alumnos inscritos en el listado del item; crea faltantes.
    """
    item = get_object_or_404(
        ListadoMateriaItem.objects.select_related("listado", "listado__programa", "materia"),
        pk=pk
    )

    # Alumnos inscritos al listado del item:
    inscripciones = (ListadoAlumno.objects
                     .filter(listado=item.listado)
                     .select_related("alumno")
                     .order_by("alumno__numero_estudiante"))
    alumnos_ids = [ins.alumno_id for ins in inscripciones]

    # Asegura que exista una calificación por alumno-inscrito
    existentes = set(Calificacion.objects.filter(item=item, alumno_id__in=alumnos_ids)
                     .values_list("alumno_id", flat=True))
    faltan_ids = [aid for aid in alumnos_ids if aid not in existentes]
    for aid in faltan_ids:
        Calificacion.objects.create(item=item, alumno_id=aid, nota=None)

    # Formset para edición masiva
    CalificacionFormSet = modelformset_factory(
        Calificacion,
        fields=("nota", "observaciones"),
        extra=0,
        can_delete=False
    )

    qs_califs = (Calificacion.objects
                 .filter(item=item, alumno_id__in=alumnos_ids)
                 .select_related("alumno")
                 .order_by("alumno__numero_estudiante"))

    if request.method == "POST":
        formset = CalificacionFormSet(request.POST, queryset=qs_califs)
        if formset.is_valid():
            formset.save()  # triggers model.save (recalcula aprobado si lo haces en save/clean)
            messages.success(request, "Calificaciones guardadas.")
            return redirect("academico:calificaciones_item", pk=item.pk)
        else:
            messages.error(request, "Revisa los errores en el formulario.")
    else:
        formset = CalificacionFormSet(queryset=qs_califs)

    return render(request, "academico/calificaciones_item.html", {
        "item": item,
        "listado": item.listado,
        "formset": formset,
        "inscripciones": inscripciones,
    })
