from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django import forms
from .models import Alumno, Programa
from django.contrib.auth.models import User, Group

from django.contrib import messages
from django.contrib.auth.models import User
from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError
from .models import Cargo, ClipPaymentOrder, Pago
from .models import Financiamiento

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4


from django.utils import timezone
from django.http import JsonResponse, Http404
from datetime import date

from .forms import  InformacionEscolarForm

from django.db.models import Q
from .models import  Pais, Estado

from django.contrib.auth.decorators import login_required

from django.contrib.auth.decorators import user_passes_test


from alumnos.permisos import user_can_view_pagos, user_can_view_documentos, user_can_edit_alumno, user_can_view_alumno

def staff_or_admisiones(u):
    return u.is_authenticated and (u.is_staff or u.groups.filter(name="admisiones").exists())

def staff_or_admisiones_required(view_func):
    return user_passes_test(staff_or_admisiones)(view_func)



#EJEMPLO
#@staff_or_admisiones_required
#def alumnos_crear(request):




# Create your views here.
####################################################################
# views.py
#from django.shortcuts import redirectt_object_or_404
from django.contrib.auth.decorators import user_passes_test
from .forms import AlumnoForm






def admin_required(view_func):
    return user_passes_test(lambda u: u.is_active and u.is_staff)(view_func)
################################################################################
from .utils import send_simple_sms, send_simple_whatsapp, siguiente_numero_estudiante

@admin_required
def alumnos_crear(request):
    if request.method == "POST":
        form = AlumnoForm(request.POST, crear=True, request=request)
        if form.is_valid():
            alumno = form.save(commit=False)  # OJO: con commit=False no se setea created_by en el form
            alumno.numero_estudiante = siguiente_numero_estudiante()

            # Parche defensivo por si la columna en BD quedó NOT NULL sin auto_now_add efectivo
            if not getattr(alumno, "creado_en", None):
                alumno.creado_en = timezone.now()

            # Como hicimos commit=False, aseguramos created_by manualmente
            if request.user.is_authenticated and not getattr(alumno, "created_by_id", None):
                alumno.created_by = request.user

            alumno.save()
            messages.success(request, "Alumno creado correctamente.")
            return redirect("alumnos_detalle", pk=alumno.pk)
    else:
        form = AlumnoForm(crear=True, request=request)

    return render(request, "alumnos/editar_alumno.html", {
        "form": form,
        "alumno": None,
        "modo": "crear",
        # "preview_numero": (ContadorAlumno.objects.first().ultimo_numero + 1) if ContadorAlumno.objects.exists() else 1,
    })
####################################################################################
# views.py (o donde tengas alumnos_editar)
from django.db.models import Sum
from alumnos.models import Alumno, PagoDiario
from django.http import HttpResponseForbidden
# Mantén este decorador si solo staff puede editar:




import logging
from django.db import transaction
from django.forms.models import model_to_dict
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib import messages
from django.db.models import Q, Sum

logger = logging.getLogger(__name__)

# ---- helper de debug para ver campos clave de InformacionEscolar ----
_INFO_FIELDS_DEBUG = [
    "programa_id", "financiamiento_id",
    "precio_colegiatura", "monto_descuento", "precio_final",
    "meses_programa", "precio_inscripcion", "precio_titulacion",
    "precio_equivalencia", "numero_reinscripciones",
    "sede_id", "inicio_programa", "fin_programa",
    "grupo", "modalidad", "matricula",
    "estatus_academico_id", "estatus_administrativo_id",
    "requiere_datos_de_facturacion",
]

def _snap_info(info):
    if not info:
        return None
    out = {}
    for f in _INFO_FIELDS_DEBUG:
        out[f] = getattr(info, f, None)
    return out

######################################################################

@admin_required
def alumnos_editar(request, pk):
    alumno = get_object_or_404(
        Alumno.objects.select_related(
            "pais", "estado",
            "informacionEscolar",
            "informacionEscolar__programa",
            "informacionEscolar__sede",
        ),
        pk=pk,
    )

    if not user_can_edit_alumno(request.user, alumno):
        return HttpResponseForbidden("No tienes permiso para editar este alumno.")

    # Panel lateral: pagos
    pagos_qs = PagoDiario.objects.filter(alumno=alumno).order_by("-fecha", "-id")
    pagos_total = pagos_qs.aggregate(total=Sum("monto"))["total"] or 0

    # Info escolar (puede no existir)
    info = getattr(alumno, "informacionEscolar", None)

    # Documentos del plan
    docs_qs = DocumentoAlumno.objects.none()
    if info:
        docs_qs = (
            DocumentoAlumno.objects
            .filter(info_escolar=info)
            .select_related("tipo", "subido_por", "verificado_por")
            .order_by("-actualizado_en", "-creado_en")
        )
    docs = list(docs_qs)
    docs_total = len(docs)
    docs_last_update = docs[0].actualizado_en if docs else None

    # Requisitos y faltantes
    faltantes, tipos_requeridos = [], []
    if info and info.programa_id:
        reqs_qs = ProgramaDocumentoRequisito.objects.filter(
            programa=info.programa, activo=True, tipo__activo=True
        ).select_related("tipo").order_by("tipo__nombre")
        reqs_qs = reqs_qs.filter(
            Q(aplica_a="todos") |
            Q(aplica_a="solo_extranjeros" if _es_extranjero(info) else "solo_nacionales")
        )
        tipos_requeridos = [r.tipo for r in reqs_qs]
        tipos_subidos_ids = {d.tipo_id for d in docs}
        faltantes = [t for t in tipos_requeridos if t.id not in tipos_subidos_ids]

    active_tab = "#pane-personales"

    # ============================ DEBUG INICIAL =============================
    logger.debug("== alumnos_editar(%s) %s ==", pk, request.method)
    logger.debug("Alumno pk=%s, tiene info_escolar? %s (id=%s)",
                 alumno.pk, bool(info), getattr(info, "id", None))
    logger.debug("POST keys: %s", sorted(list(request.POST.keys())))
    print("[DEBUG] alumnos_editar:", request.method, "POST keys:", sorted(list(request.POST.keys())))

    DOCS_PREFIX = "docs"

    # =============================================================
    # POST
    # =============================================================
    if request.method == "POST":
        if "add" in request.POST:
            # --------- A) AGREGAR DOCUMENTO ----------
            if not info or not info.programa_id:
                messages.error(
                    request,
                    "Asigna primero un Programa en Información Escolar para agregar documentos."
                )
                return redirect("alumnos_editar", pk=alumno.pk)

            create_form = DocumentoAlumnoCreateForm(request.POST, request.FILES, info_escolar=info)
            form = AlumnoForm(instance=alumno, request=request)
            form_info = InformacionEscolarForm(instance=info, request=request, readonly_prices=False)
            # Para re-render, mantenemos el mismo prefix
            formset = DocumentoAlumnoFormSet(queryset=docs_qs, prefix=DOCS_PREFIX)

            logger.debug("CreateForm valid? %s", create_form.is_valid())
            if not create_form.is_valid():
                logger.debug("CreateForm errors: %s", create_form.errors)
                print("[DEBUG] CreateForm errors:", create_form.errors)

            if create_form.is_valid():
                nuevo = create_form.save(commit=False)
                if getattr(nuevo, "archivo", None) and not nuevo.subido_por_id:
                    nuevo.subido_por = request.user
                nuevo.info_escolar = info
                nuevo.save()
                messages.success(request, f"Documento '{nuevo.tipo.nombre}' subido correctamente.")
                return redirect("alumnos_editar", pk=alumno.pk)

            messages.error(request, "Revisa los errores al agregar el documento.")
            active_tab = "#pane-plan"

        else:
            # --------- B) GUARDAR CAMBIOS (alumno + info + formset) ----------
            form = AlumnoForm(request.POST, instance=alumno, request=request)
            form_info = InformacionEscolarForm(
                request.POST,
                instance=info,
                request=request,
                readonly_prices=False,
            )

            # Detecta si realmente viene el formset en el POST (management form)
            has_docs_in_post = any(k.startswith(f"{DOCS_PREFIX}-") for k in request.POST.keys())

            if has_docs_in_post:
                formset = DocumentoAlumnoFormSet(
                    request.POST, request.FILES, queryset=docs_qs, prefix=DOCS_PREFIX
                )
            else:
                # No viene el formset: no debe bloquear validación ni guardado
                formset = DocumentoAlumnoFormSet(queryset=docs_qs, prefix=DOCS_PREFIX)

            create_form = DocumentoAlumnoCreateForm(info_escolar=info)

            # ---- DEBUG de valores que llegan para info escolar ----
            campos_info_post = [k for k in request.POST.keys() if k.startswith("inicio_programa") or k in [
                "programa", "financiamiento",
                "precio_colegiatura", "monto_descuento", "precio_final",
                "meses_programa",
                "precio_inscripcion", "precio_reinscripcion",
                "precio_titulacion", "precio_equivalencia",
                "numero_reinscripciones",
                "sede", "fin_programa", "grupo", "modalidad",
                "matricula",
                "estatus_academico", "estatus_administrativo",
                "requiere_datos_de_facturacion",
            ]]
            logger.debug("POST (campos info escolar) -> %s", {k: request.POST.get(k) for k in campos_info_post})
            print("[DEBUG] POST info-escolar ->", {k: request.POST.get(k) for k in campos_info_post})

            # === VALIDACIONES ===
            is_valid_alumno  = form.is_valid()
            is_valid_info    = form_info.is_valid()
            is_valid_formset = formset.is_valid() if has_docs_in_post else True

            logger.debug("AlumnoForm is_valid? %s", is_valid_alumno)
            logger.debug("AlumnoForm errors: %s", form.errors)

            logger.debug("InfoForm is_valid? %s", is_valid_info)
            logger.debug("InfoForm errors: %s", form_info.errors)
            logger.debug("InfoForm non_field_errors: %s", form_info.non_field_errors())

            logger.debug("DocsFormset (checked=%s) is_valid? %s", has_docs_in_post, is_valid_formset)
            if has_docs_in_post and not is_valid_formset:
                logger.debug("DocsFormset errors: %s", formset.errors)

            if is_valid_alumno and is_valid_info and is_valid_formset:
                pre_snap = _snap_info(info)
                logger.debug("SNAP antes de save() -> %s", pre_snap)
                print("[DEBUG] SNAP antes de save:", pre_snap)

                try:
                    with transaction.atomic():
                        alumno = form.save()

                        # Guardar o crear info escolar
                        info_obj = form_info.save(commit=False)
                        info_obj.alumno = alumno
                        logger.debug("InfoForm cleaned_data -> %s", form_info.cleaned_data)
                        print("[DEBUG] InfoForm cleaned_data ->", form_info.cleaned_data)

                        info_obj.save()
                        logger.debug("Info obj guardado id=%s", info_obj.id)
                        print("[DEBUG] Info obj guardado id=", info_obj.id)

                        # Enlazar si no estaba enlazado aún
                        if not alumno.informacionEscolar_id:
                            alumno.informacionEscolar = info_obj
                            alumno.save(update_fields=["informacionEscolar"])
                            logger.debug("Alumno enlazado a info_escolar id=%s", info_obj.id)
                            print("[DEBUG] Alumno enlazado a info_escolar id=", info_obj.id)

                        # Guardar documentos existentes (formset) SOLO si vino en POST
                        if has_docs_in_post:
                            instances = formset.save(commit=False)
                            for inst in instances:
                                if getattr(inst, "archivo", None) and not inst.subido_por_id:
                                    inst.subido_por = request.user
                                inst.info_escolar = info_obj
                                inst.save()
                            for f in formset.deleted_forms:
                                if f.instance.pk:
                                    f.instance.delete()

                    # Refetch info para snapshot posterior
                    info_refetch = getattr(alumno, "informacionEscolar", None)
                    post_snap = _snap_info(info_refetch)
                    logger.debug("SNAP después de save() -> %s", post_snap)
                    print("[DEBUG] SNAP después de save:", post_snap)

                except Exception as e:
                    logger.exception("Excepción guardando alumno/info: %s", e)
                    print("[DEBUG][EXCEPTION] guardando alumno/info:", repr(e))
                    messages.error(request, f"Error al guardar: {e}")
                else:
                    messages.success(request, "Alumno e información escolar actualizados correctamente.")
                    #return redirect("alumnos_editar", pk=alumno.pk)
                    return redirect("alumnos_detalle", pk=alumno.pk) 

            # Si hubo errores, decidir tab activo
            if not is_valid_info or (has_docs_in_post and not is_valid_formset):
                active_tab = "#pane-plan"
            elif not is_valid_alumno:
                active_tab = "#pane-personales"

    # =============================================================
    # GET
    # =============================================================
    else:
        form = AlumnoForm(instance=alumno, request=request)
        form_info = InformacionEscolarForm(instance=info, request=request, readonly_prices=False)
        formset = DocumentoAlumnoFormSet(queryset=docs_qs, prefix=DOCS_PREFIX)
        create_form = DocumentoAlumnoCreateForm(info_escolar=info)

        logger.debug("GET: snapshot info escolar -> %s", _snap_info(info))
        print("[DEBUG] GET snapshot info escolar:", _snap_info(info))

    # =============================================================
    # RENDER
    # =============================================================
    return render(
        request,
        "alumnos/editar_alumno.html",
        {
            "modo": "editar",
            "alumno": alumno,
            "form": form,
            "form_info": form_info,
            "formset": formset,
            "create_form": create_form,
            "docs_total": docs_total,
            "docs_last_update": docs_last_update,
            "faltantes": faltantes,
            "tipos_requeridos": tipos_requeridos,
            "pagos": pagos_qs,
            "pagos_total": pagos_total,
            "active_tab": active_tab,
        },
    )


####################################################################

from django.contrib.auth.views import LoginView

class LoginViewRemember(LoginView):
    template_name = "accounts/login.html"

    def form_valid(self, form):
        remember = self.request.POST.get("remember") == "on"
        response = super().form_valid(form)
        if remember:
            # 2 semanas
            self.request.session.set_expiry(1209600)
        else:
            # expira al cerrar navegador
            self.request.session.set_expiry(0)
        return response
###############################################################
from django.shortcuts import render
from datetime import date, timedelta
import json
from math import ceil
from .models import UserProfile


def _filtrar_por_permisos_sede(qs, user):
    """
    Filtra el queryset de alumnos según los permisos de sede del usuario.
    - superuser => ve todo
    - si tiene sedes asignadas => ve sólo esas sedes
    - puede_ver_todo / puede_editar_todo => no limita por rol, pero sí por sedes asignadas
    - sin perfil o sin sedes => no ve nada
    """
    if not user.is_authenticated:
        return qs.none()

    if user.is_superuser:
        return qs  # acceso total

    try:
        profile = user.profile
    except UserProfile.DoesNotExist:
        return qs.none()

    # SedES asignadas al usuario
    sedes_ids = list(profile.sedes.values_list("id", flat=True))

    if not sedes_ids:
        # si no tiene sedes asignadas, no puede ver nada
        return qs.none()

    # Aquí definimos el filtro de base: sólo las sedes asignadas
    filtro = Q(informacionEscolar__sede_id__in=sedes_ids)

    # Si tiene editar/ver todo, no filtramos más por "alcance total del sistema",
    # solo le permitimos trabajar libremente dentro de sus sedes.
    return qs.filter(filtro)

###############################################################
from django.db.models import Case, When, Value, BooleanField
@login_required
def estudiantes(request):
    q = (request.GET.get("q") or "").strip()

    hoy = timezone.localdate()

    qs = (
        Alumno.for_user(request.user)
        .select_related(
            "pais", "estado",
            "informacionEscolar",
            "informacionEscolar__programa",
            "informacionEscolar__sede",
            "user",
        )
        .annotate(
            # Activo si fin_programa es FUTURO; si es hoy o pasado (o null), NO activo
            activo=Case(
                When(informacionEscolar__fin_programa__gt=hoy, then=Value(True)),
                default=Value(False),
                output_field=BooleanField(),
            )
        )
    )

    if q:
        qs = qs.filter(
            Q(numero_estudiante__icontains=q) |
            Q(nombre__icontains=q) |
            Q(apellido_p__icontains=q) |
            Q(apellido_m__icontains=q) |
            Q(email__icontains=q) |
            Q(curp__icontains=q)
        )

    profile = getattr(request.user, "profile", None)

    return render(
        request,
        "panel/all_orders.html",
        {"alumnos": qs, "q": q, "p": profile},
    )
###############################################################
# views.py
import re
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required

# importa tu función real:
# from .curp_scraper import datos_desde_gobmx_curp

CURP_RE = re.compile(r"^[A-Z]{4}\d{6}[HM][A-Z]{5}[A-Z0-9]\d$")

@login_required
@require_POST
def api_curp_lookup(request):
    from alumnos.utils import datos_desde_gobmx_curp

    curp = (request.POST.get("curp") or "").strip().upper()

    if not CURP_RE.match(curp):
        return JsonResponse({"ok": False, "error": "CURP inválido."}, status=400)

    try:
        # Llama a tu scraper/lógica que devuelve un dict:
        # {
        #   "CURP": "...",
        #   "Nombre": "YATNIEL",
        #   "PrimerApellido": "GONZÁLEZ",
        #   "SegundoApellido": "HERNÁNDEZ",
        #   "Sexo": "HOMBRE",
        #   "FechaNacimiento": "12/05/1984",
        #   "Nacionalidad": "...",
        #   "EntidadNacimiento": "..."
        # }
        data = datos_desde_gobmx_curp(curp)
        if not data or "Nombre" not in data:
            return JsonResponse({"ok": False, "error": "No se pudo obtener datos para ese CURP."}, status=502)

        return JsonResponse({"ok": True, "data": data})
    except Exception as e:
        return JsonResponse({"ok": False, "error": f"Falla al consultar: {e}"}, status=500)

###############################################################

@login_required   
def principal(request):
    # SMS a un número específico:
    #msg = send_simple_sms("Hola desde CampusIUAF 🚀", "+529931691530")
    #print(msg.sid, msg.status)

    # WhatsApp a un número específico:
    #msg2 = send_simple_whatsapp("Hola por WhatsApp 👋", "+529931691530")
    #print(msg2.sid, msg2.status)

    # Forzar entorno 'prod' (si tienes dos TwilioConfig, una sandbox y otra prod):
    #msg3 = send_simple_sms("Mensaje en prod", "+529931691530", env="prod")

    # =========================
    # 1) Ventas mensuales (Bar)
    # =========================
    meses_labels = ["Ene", "Feb", "Mar", "Abr", "May", "Jun",
                    "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
    # Ventas simuladas por mes
    meses_ventas = [120, 150, 90, 180, 220, 170, 210, 260, 190, 230, 200, 280]

    # Para el texto del footer del primer card
    prendas_mes =  sum(meses_ventas[date.today().month-1:date.today().month]) or meses_ventas[date.today().month-1]

    # =================================
    # 2) Pedidos diarios últimos 7 días
    # =================================
    hoy = date.today()
    ultimos_7 = [hoy - timedelta(days=d) for d in range(6, -1, -1)]
    # Etiquetas tipo "08/10"
    dias_pedidos = [f"{d.day:02}/{d.month:02}" for d in ultimos_7]
    # Totales simulados
    totales_pedidos = [8, 12, 10, 14, 9, 11, 15]

    pedidos_hoy = totales_pedidos[-1]
    pedidos_ayer = totales_pedidos[-2]
    if pedidos_ayer == 0:
        porcentaje_cambio_pedidos_hoy = 100 if pedidos_hoy > 0 else 0
    else:
        porcentaje_cambio_pedidos_hoy = round(((pedidos_hoy - pedidos_ayer) / pedidos_ayer) * 100, 2)

    total_pedidos_semana = sum(totales_pedidos)

    # ==========================================
    # 3) (Opcional) Evolución semanal/total anual
    #    Tu template usa datos fijos; si quieres,
    #    aquí podrías calcularlos y luego ajustar
    #    el template para leerlos.
    # ==========================================
    # ejemplo_simple_evolucion = [120, 180, 160, 200, 150, 210, 190, 220, 240, 260, 230, 250]
    

    ventas_simuladas = { 
        "MX - México":            852250,
       # "MX - Toluca":             420,
       # "MX - Ciudad del C.":      980,   # CDMX
       # "MX - Kantunilkin":        210,
       # "MX - Kantukilkin":        80,    # error de escritura conservado
       # "MX - Puerto M.":          360,   # Puerto Morelos
       # "MX - Chetumal":           190,
       # "MX - Chiapas":            270,
        "GT - Guatemala":          158500,
        "PA - Panamá":              85690,
        #"MX - Monterrey":          310,
        #"MX - Saltillo":           140,
#        "UN - Por identificar":     60,   # usará bandera "un"
    }

    total_general = sum(ventas_simuladas.values())

    # Construimos la lista que usa tu template: pais, total_vendido, porcentaje
    ventas_por_pais = []
    for etiqueta, valor in ventas_simuladas.items():
        ventas_por_pais.append({
            "pais": etiqueta,                       # p.ej. "MX - Cancún"
            "total_vendido": valor,
            "porcentaje": round((valor/total_general)*100, 2) if total_general else 0,
        })

    # Orden descendente por ventas (opcional)
    ventas_por_pais.sort(key=lambda r: r["total_vendido"], reverse=True)

    context = {
        # Gráfica 1 (mensual)
        "meses_labels": json.dumps(meses_labels),
        "meses_ventas": json.dumps(meses_ventas),
        "prendas_mes": prendas_mes,

        # Gráfica 2 (diaria)
        "dias_pedidos": json.dumps(dias_pedidos),
        "totales_pedidos": json.dumps(totales_pedidos),
        "porcentaje_cambio_pedidos_hoy": porcentaje_cambio_pedidos_hoy,
        "pedidos_hoy": pedidos_hoy,
        "pedidos_ayer": pedidos_ayer,
        "total_pedidos_semana": total_pedidos_semana,

        "ventas_por_pais": ventas_por_pais,
        # Si tu template muestra otros contadores, ponles defaults:
        #"prendas_mes": total_general,                 # por si lo usas en un footer        
        "porcentaje_cambio_pedidos_hoy": 0,
        "pedidos_hoy": 0, "pedidos_ayer": 0,
        "total_pedidos_semana": 0,

        # Si más adelante conectas la 3ra gráfica:
        # "evolucion_anual": json.dumps(ejemplo_simple_evolucion),
    }
    return render(request, "panel/principal.html", context)








###############################################################
# alumnos_lista()
@login_required
def alumnos_lista(request):
    q = (request.GET.get("q") or "").strip()
    qs = Alumno.for_user(request.user)  # <- AQUÍ
    if q:
        qs = qs.filter(
            Q(numero_estudiante__icontains=q) |
            Q(nombre__icontains=q) |
            Q(apellido_p__icontains=q) |
            Q(apellido_m__icontains=q) |
            Q(email__icontains=q) |
            Q(curp__icontains=q)
        )
    return render(request, "alumnos/lista.html", {"alumnos": qs, "q": q})


###############################################################
from .models import  ProgramaDocumentoRequisito, DocumentoAlumno
from django.db.models import Max

@login_required
def alumnos_detalle(request, pk):
    alumno = get_object_or_404(
        Alumno.objects.select_related(
            "pais", "estado", "informacionEscolar",
            "informacionEscolar__programa", "informacionEscolar__sede",
        ),
        pk=pk,
    )

    # -------- Permisos de visualización del alumno --------
    user = request.user
    can_view = False
    if user.is_superuser:
        can_view = True
    elif user.groups.filter(name="admisiones").exists():
        can_view = (alumno.created_by_id == user.id)
    else:
        profile = getattr(user, "profile", None)
        if profile:
            sede_id = getattr(getattr(alumno, "informacionEscolar", None), "sede_id", None)
            if sede_id and profile.sedes.filter(id=sede_id).exists():
                can_view = True
    if not can_view:
        return HttpResponseForbidden("No tienes permiso para ver este alumno.")

    # -------- Flags por permiso/grupo --------
    can_view_pagos = user_can_view_pagos(user)
    can_view_docs  = user_can_view_documentos(user)

    # -------- Pagos / Cargos (solo si puede ver) --------
    pagos = cargos = cargos_pendientes = None
    pagos_total = 0
    if can_view_pagos:
        pagos = (
            PagoDiario.objects
            .filter(alumno=alumno)
            .order_by("fecha", "-id")
        )
        pagos_total = round(pagos.aggregate(total=Sum("monto"))["total"] or 0, 2)

        cargos = (
            Cargo.objects
            .filter(alumno=alumno)
            .select_related("concepto")
            .order_by("-fecha_cargo", "-id")
        )
        cargos_pendientes = cargos.filter(pagado=False)

    # -------- Documentos DINÁMICOS por programa --------
    docs = []
    docs_total = 0
    docs_last_update = None
    faltantes = []

    info = getattr(alumno, "informacionEscolar", None)
    prog = getattr(info, "programa", None)

    # <<< NUEVO: flag para “Fin del programa en futuro” >>>
    fin_programa_is_future = False
    if info and getattr(info, "fin_programa", None):
        hoy = timezone.localdate()
        # Si fin_programa es DateField -> comparación directa
        fin_programa_is_future = info.fin_programa > hoy
    # <<< FIN NUEVO >>>

    if can_view_docs and info and prog:
        # Documentos subidos para el plan escolar del alumno
        docs_qs = (
            DocumentoAlumno.objects
            .filter(info_escolar=info)
            .select_related("tipo", "verificado_por", "subido_por")
            .order_by("-actualizado_en")  # usar actualizado_en
        )
        docs = list(docs_qs)
        docs_total = len(docs)
        agg = docs_qs.aggregate(ultima=Max("actualizado_en"))
        docs_last_update = agg["ultima"]

        # Tipos requeridos por el PROGRAMA (activos)
        reqs = (
            ProgramaDocumentoRequisito.objects
            .filter(programa=prog, activo=True)
            .select_related("tipo")
        )
        req_tipos = [r.tipo for r in reqs]

        # Ids de tipos ya subidos
        subidos_tipo_ids = {d.tipo_id for d in docs if d.tipo_id}

        # Faltantes = tipos requeridos cuyo id no está en subidos
        faltantes = [t for t in req_tipos if t.id not in subidos_tipo_ids]

    return render(
        request,
        "alumnos/detalle.html",
        {
            "alumno": alumno,

            # pagos/cargos
            "pagos": pagos,
            "pagos_total": pagos_total,
            "cargos": cargos,
            "cargos_pendientes": cargos_pendientes,
            "can_view_pagos": can_view_pagos,

            # documentos dinámicos
            "can_view_documentos": can_view_docs,
            "docs": docs,
            "docs_total": docs_total,
            "docs_last_update": docs_last_update,
            "faltantes": faltantes,

            # <<< NUEVO en el contexto para pintar en el template >>>
            "fin_programa_is_future": fin_programa_is_future,
        },
    )

###############################################################
@login_required   
def alumnos_crear11(request):
    if request.method == "POST":
        form = AlumnoForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect(reverse("alumnos_lista"))
    else:
        form = AlumnoForm()
    return render(request, "alumnos/form.html", {"form": form, "modo": "Crear"})

###############################################################
@login_required   
def alumnos_editar11(request, pk):
    alumno = get_object_or_404(Alumno, pk=pk)
    if request.method == "POST":
        form = AlumnoForm(request.POST, instance=alumno)
        if form.is_valid():
            form.save()
            return redirect(reverse("alumnos_detalle", args=[alumno.pk]))
    else:
        form = AlumnoForm(instance=alumno)
    return render(request, "alumnos/form.html", {"form": form, "modo": "Editar"})

###############################################################
@login_required   
class CrearUsuarioAlumnoForm(forms.Form):
    username = forms.CharField(max_length=150, help_text="Sugerido: número de estudiante")
    email = forms.EmailField(required=False)
    password1 = forms.CharField(widget=forms.PasswordInput, label="Contraseña")
    password2 = forms.CharField(widget=forms.PasswordInput, label="Confirmar contraseña")
    grupos = forms.ModelMultipleChoiceField(
        queryset=Group.objects.all().order_by("name"),
        required=False,
        help_text="Selecciona uno o varios roles (grupos) para este usuario."
    )

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get("password1")
        p2 = cleaned.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", "Las contraseñas no coinciden.")
        # Opcional: validaciones de fuerza de contraseña aquí
        return cleaned
    

###############################################################
@login_required   
def alumnos_crear_usuario(request, pk):
    alumno = get_object_or_404(Alumno, pk=pk)

    # Si ya tiene usuario vinculado, puedes redirigir o permitir reasignar
    if alumno.user:
        messages.info(request, "Este alumno ya tiene un usuario asignado.")
        return redirect(reverse("alumnos_detalle", args=[alumno.pk]))

    if request.method == "POST":
        form = CrearUsuarioAlumnoForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data["username"].strip()
            email = form.cleaned_data.get("email", "").strip()
            password1 = form.cleaned_data["password1"]
            grupos = form.cleaned_data["grupos"]

            if User.objects.filter(username=username).exists():
                form.add_error("username", "Ese nombre de usuario ya existe.")
            else:
                # Valida la contraseña con validadores de Django
                try:
                    password_validation.validate_password(password1)
                except ValidationError as e:
                    form.add_error("password1", e)
                else:
                    user = User.objects.create_user(username=username, email=email or alumno.email or "")
                    user.set_password(password1)
                    user.first_name = alumno.nombre
                    user.last_name = f"{alumno.apellido_p} {alumno.apellido_m}".strip()
                    user.save()

                    # Asignar grupos (roles)
                    if grupos:
                        user.groups.set(grupos)

                    # Vincular al alumno si agregaste el OneToOne
                    alumno.user = user
                    alumno.save(update_fields=["user"])

                    messages.success(request, "Usuario creado y vinculado correctamente.")
                    return redirect(reverse("alumnos_detalle", args=[alumno.pk]))
    else:
        sugerido = alumno.numero_estudiante
        form = CrearUsuarioAlumnoForm(initial={
            "username": sugerido,
            "email": alumno.email or "",
        })

    return render(request, "alumnos/crear_usuario.html", {"alumno": alumno, "form": form})    

#################################################
@login_required
def documentos_alumno_editar(request, numero_estudiante):
    """
    Pantalla de documentos:
      - Alta de un nuevo documento (tipo + archivo)
      - Edición / reemplazo / eliminación de documentos existentes (formset)
    """
    # Si numero_estudiante es realmente el PK, esto está bien.
    # Si tu clave es otro campo (p.ej. numero_estudiante único), cambia la línea:
    # alumno = get_object_or_404(Alumno, numero_estudiante=numero_estudiante)
    alumno = get_object_or_404(Alumno, pk=numero_estudiante)

    # Permiso de acceso a documentos
    if not user_can_view_documentos(request.user):
        return HttpResponseForbidden("No tienes permiso para ver documentos.")

    info = getattr(alumno, "informacionEscolar", None)

    # Documentos existentes del plan escolar
    docs_qs = DocumentoAlumno.objects.none()
    if info:
        docs_qs = (
            DocumentoAlumno.objects
            .filter(info_escolar=info)
            .select_related("tipo", "subido_por")
            .order_by("-actualizado_en", "-id")
        )

    # Métricas rápidas
    docs_total = docs_qs.count()
    docs_last_update = docs_qs.aggregate(m=Max("actualizado_en"))["m"]

    # Tipos faltantes según requisitos y nacionalidad
    faltantes = []
    if info and info.programa_id:
        reqs = (
            ProgramaDocumentoRequisito.objects
            .filter(programa=info.programa, activo=True, tipo__activo=True)
            .select_related("tipo")
        )
        if _es_extranjero(info):
            reqs = reqs.filter(Q(aplica_a="todos") | Q(aplica_a="solo_extranjeros"))
        else:
            reqs = reqs.filter(Q(aplica_a="todos") | Q(aplica_a="solo_nacionales"))

        tipos_requeridos_ids = set(reqs.values_list("tipo_id", flat=True))
        tipos_presentes_ids  = set(docs_qs.values_list("tipo_id", flat=True))
        faltantes_ids = tipos_requeridos_ids - tipos_presentes_ids
        if faltantes_ids:
            faltantes = list(
                DocumentoTipo.objects.filter(id__in=faltantes_ids).order_by("nombre")
            )

    # ------------ Formularios ------------
    # Alta de un documento
    if request.method == "POST" and "add" in request.POST:
        create_form = DocumentoAlumnoCreateForm(request.POST, request.FILES, info_escolar=info)
    else:
        create_form = DocumentoAlumnoCreateForm(info_escolar=info)

    # Formset edición/eliminación (nota: usamos prefix fijo "docs")
    if request.method == "POST" and "add" not in request.POST:
        formset = DocumentoAlumnoFormSet(request.POST, request.FILES, queryset=docs_qs, prefix="docs")
    else:
        formset = DocumentoAlumnoFormSet(queryset=docs_qs, prefix="docs")

    # ------------ POST ------------
    if request.method == "POST":
        # A) Alta
        if "add" in request.POST:
            if not info or not info.programa_id:
                messages.error(request, "El alumno no tiene un Programa asignado.")
            elif create_form.is_valid():
                obj = create_form.save(commit=False)
                obj.subido_por = request.user
                obj.info_escolar = info
                obj.save()
                messages.success(request, "Documento agregado correctamente.")
                return redirect("alumnos_documentos_editar", pk=alumno.pk)
            else:
                messages.error(request, "Revisa los errores del formulario de alta.")
        # B) Edición / eliminación
        else:
            if formset.is_valid():
                # 1) Eliminar los marcados (en ModelFormSet se usa deleted_forms)
                for f in formset.deleted_forms:
                    if f.instance.pk:
                        f.instance.delete()

                # 2) Guardar los restantes que cambiaron
                for f in formset.forms:
                    if f in formset.deleted_forms:
                        continue
                    if f.has_changed():
                        inst = f.save(commit=False)
                        # Si reemplazaron archivo, marcar quién sube
                        if f.cleaned_data.get("archivo"):
                            inst.subido_por = request.user
                        inst.info_escolar = info  # por seguridad
                        inst.save()

                messages.success(request, "Cambios guardados.")
                return redirect("alumnos_documentos_editar", pk=alumno.pk)
            else:
                messages.error(request, "Revisa los errores de los documentos cargados.")

    # Render
    return render(
        request,
        "alumnos/documentos_form.html",
        {
            "alumno": alumno,
            "info": info,
            "create_form": create_form,
            "formset": formset,
            "docs_total": docs_total,
            "docs_last_update": docs_last_update,
            "faltantes": faltantes,
        },
    )
###########################################################################################################
from django.utils.decorators import method_decorator
from django.views.generic import ListView
from .models import PagoDiario

@method_decorator(login_required, name="dispatch")
class PagoDiarioListView(ListView):
    model = PagoDiario
    template_name = "alumnos/pagos_diario_list.html"
    context_object_name = "pagos"
    paginate_by = None

    def get_queryset(self):
        # Base + evitar filas sin alumno
        qs = (
            PagoDiario.objects
            .select_related("alumno")
            .filter(alumno__isnull=False)
            .order_by("-fecha", "-id")
        )

        user = self.request.user

        # Debe pertenecer al grupo "pagos" (salvo superuser)
        if not user.is_superuser and not user.groups.filter(name="pagos").exists():
            return qs.none()

        # Superuser: ve todo
        if user.is_superuser:
            base_qs = qs
        else:
            allowed = None  # ⚠️ NO usar Q() vacío

            # Si es admisiones: solo pagos de alumnos creados por él
            if user.groups.filter(name="admisiones").exists():
                cond = Q(alumno__created_by=user)
                allowed = cond if allowed is None else (allowed | cond)

            # Además: pagos de sedes asociadas a su perfil (si tiene)
            profile = getattr(user, "profile", None)
            if profile:
                sedes_ids = list(profile.sedes.values_list("id", flat=True))
                if sedes_ids:
                    cond = Q(alumno__informacionEscolar__sede_id__in=sedes_ids)
                    allowed = cond if allowed is None else (allowed | cond)

            # Si no hay nada permitido => nada
            if allowed is None:
                return qs.none()

            base_qs = qs.filter(allowed).distinct()

        # Límite temporal (2 años) salvo flag en perfil
        profile = getattr(user, "profile", None)
        show_all = bool(profile and getattr(profile, "ver_todos_los_pagos", False))
        if not show_all:
            hace_dos_anios = timezone.now().date() - timedelta(days=730)
            base_qs = base_qs.filter(fecha__gte=hace_dos_anios)

        # Búsqueda libre
        q = (self.request.GET.get("q") or "").strip()
        if q:
            base_qs = base_qs.filter(
                Q(alumno__numero_estudiante__icontains=q) |
                Q(alumno__nombre__icontains=q) |
                Q(alumno__apellido_p__icontains=q) |
                Q(alumno__apellido_m__icontains=q) |
                Q(curp__icontains=q) |
                Q(folio__icontains=q) |
                Q(concepto__icontains=q) |
                Q(programa__icontains=q)
            )

        return base_qs
    
############################################################################################################

@login_required
def programa_info(request, pk):
    p = get_object_or_404(Programa, pk=pk)

    # soporta p.reinscripcion o p.precio_reinscripcion
    rein_val = getattr(p, "reinscripcion", None)
    if rein_val is None:
        rein_val = getattr(p, "precio_reinscripcion", None)
    if rein_val is None:
        rein_val = Decimal("0.00")

    data = {
        "meses_programa": p.meses_programa,
        "precio_colegiatura": str(p.colegiatura),
        "precio_inscripcion": str(p.inscripcion),
        "precio_reinscripcion": str(rein_val),  # ⬅️
        "precio_titulacion": str(p.titulacion),
        "precio_equivalencia": str(p.equivalencia),
        "numero_reinscripciones": 0,
    }
    return JsonResponse(data)

###############################################################
@admin_required
def api_financiamiento(request, pk):
    try:
        f = Financiamiento.objects.get(pk=pk)
    except Financiamiento.DoesNotExist:
        raise Http404("Financiamiento no encontrado")

    data = {
        "id": f.id,
        "tipo": getattr(f, "tipo_descuento", None),                # "porcentaje" | "monto"
        "porcentaje": float(getattr(f, "porcentaje_descuento", 0) or 0),
        "monto": float(getattr(f, "monto_descuento", 0) or 0),
    }
    return JsonResponse(data)


###########################################################################
# views.py
#from django.contrib import messages
#from django.contrib.auth.decorators import login_required
#from django.db.models import Q
#from django.http import HttpResponseForbidden
#from django.shortcuts import get_object_or_404, redirect, render

from .models import (
 #   Alumno,
    InformacionEscolar,
 #   DocumentoAlumno,
    DocumentoTipo,
 #   ProgramaDocumentoRequisito,
)
from .forms import (
    DocumentoAlumnoCreateForm,
    DocumentoAlumnoFormSet,
)
from .permisos import user_can_view_documentos  # ya lo usas

def _es_extranjero(info: InformacionEscolar) -> bool:
    if not info:
        return False
    alumno = getattr(info, "alumno", None)
    if not alumno or not alumno.pais:
        return False
    iso2 = (alumno.pais.codigo_iso2 or "").upper()
    return bool(iso2 and iso2 != "MX")


@login_required
def alumnos_documentos_editar(request, pk):
    if not user_can_view_documentos(request.user):
        return HttpResponseForbidden("No tienes permiso para ver documentos.")

    alumno = get_object_or_404(
        Alumno.objects.select_related(
            "pais",
            "informacionEscolar",
            "informacionEscolar__programa",
        ),
        pk=pk,
    )
    info = alumno.informacionEscolar

    if not info or not info.programa_id:
        messages.warning(request, "Este alumno no tiene Programa asignado; no hay requisitos para mostrar.")
        return render(request, "alumnos/documentos_form.html", {
            "alumno": alumno,
            "info": info,
            "create_form": None,
            "formset": None,
            "docs": [],
            "faltantes": [],
            "docs_total": 0,
            "docs_last_update": None,
            "tipos_requeridos": [],
        })

    docs_qs = (DocumentoAlumno.objects
               .filter(info_escolar=info)
               .select_related("tipo", "subido_por", "verificado_por")
               .order_by("-actualizado_en", "-creado_en"))
    docs = list(docs_qs)

    # requisitos (filtrados por nacionalidad)
    reqs_qs = ProgramaDocumentoRequisito.objects.filter(
        programa=info.programa, activo=True, tipo__activo=True
    ).select_related("tipo").order_by("tipo__nombre")
    reqs_qs = reqs_qs.filter(
        Q(aplica_a="todos") |
        Q(aplica_a="solo_extranjeros" if _es_extranjero(info) else "solo_nacionales")
    )
    tipos_requeridos = [r.tipo for r in reqs_qs]
    tipos_subidos_ids = set(d.tipo_id for d in docs)
    faltantes = [t for t in tipos_requeridos if t.id not in tipos_subidos_ids]

    docs_total = len(docs)
    docs_last_update = docs[0].actualizado_en if docs else None

    if request.method == "POST":
        if "add" in request.POST:
            create_form = DocumentoAlumnoCreateForm(request.POST, request.FILES, info_escolar=info)
            formset = DocumentoAlumnoFormSet(request.POST, request.FILES, queryset=docs_qs)
            if create_form.is_valid():
                nuevo = create_form.save(commit=False)
                nuevo.subido_por = request.user
                nuevo.save()
                messages.success(request, f"Documento '{nuevo.tipo.nombre}' subido correctamente.")
                return redirect("alumnos_documentos_editar", pk=alumno.pk)
            else:
                messages.error(request, "Revisa los errores al agregar el documento.")
        else:
            create_form = DocumentoAlumnoCreateForm(info_escolar=info)
            formset = DocumentoAlumnoFormSet(request.POST, request.FILES, queryset=docs_qs)

            if formset.is_valid():
                # ✅ 1) Eliminar los marcados correctamente
                for f in formset.deleted_forms:
                    if f.instance and f.instance.pk:
                        f.instance.delete()

                # ✅ 2) Guardar/actualizar el resto
                for f in formset.forms:
                    if f in formset.deleted_forms:
                        continue
                    if not f.cleaned_data:
                        continue
                    inst = f.save(commit=False)
                    # Si reemplazaron archivo, registrar quién sube
                    if f.cleaned_data.get("archivo"):
                        inst.subido_por = request.user
                    inst.info_escolar = info  # por seguridad
                    inst.save()

                messages.success(request, "Cambios guardados correctamente.")
                return redirect("alumnos_documentos_editar", pk=alumno.pk)
            else:
                messages.error(request, "Revisa los errores del formulario de documentos.")
    else:
        create_form = DocumentoAlumnoCreateForm(info_escolar=info)
        formset = DocumentoAlumnoFormSet(queryset=docs_qs)

    return render(request, "alumnos/documentos_form.html", {
        "alumno": alumno,
        "info": info,
        "docs": docs,
        "faltantes": faltantes,
        "docs_total": docs_total,
        "docs_last_update": docs_last_update,
        "create_form": create_form,
        "formset": formset,
        "tipos_requeridos": tipos_requeridos,
    })
###############################################################
@login_required
def documentos_alumnos_lista(request):
    from alumnos.services.documentos_helpers import requisitos_para_alumno

    q = (request.GET.get("q") or "").strip()
    solo_faltantes = (request.GET.get("solo_faltantes") == "1")  # << NUEVO
    user = request.user

    alumnos_qs = (
        Alumno.for_user(user)
        .select_related(
            "pais",
            "informacionEscolar",
            "informacionEscolar__programa",
            "informacionEscolar__sede",
        )
        .prefetch_related("informacionEscolar__documentos__tipo")
        .order_by("-actualizado_en", "-numero_estudiante")
    )

    if not user_can_view_documentos(user):
        alumnos_qs = alumnos_qs.none()

    if q:
        alumnos_qs = alumnos_qs.filter(
            Q(numero_estudiante__icontains=q)
            | Q(nombre__icontains=q)
            | Q(apellido_p__icontains=q)
            | Q(apellido_m__icontains=q)
            | Q(curp__icontains=q)
            | Q(email__icontains=q)
            | Q(email_institucional__icontains=q)
        )

    items = []
    for a in alumnos_qs:
        ie = getattr(a, "informacionEscolar", None)
        prog = getattr(ie, "programa", None)

        reqs = list(requisitos_para_alumno(prog, a))
        req_tipos = [r.tipo for r in reqs]

        docs = list(ie.documentos.select_related("tipo").all()) if ie else []
        tipos_subidos_ids = {d.tipo_id for d in docs if d.tipo_id}
        faltantes = [t for t in req_tipos if t.id not in tipos_subidos_ids]

        # << NUEVO: si pediste solo faltantes y este alumno no tiene, sáltalo
        if solo_faltantes and not faltantes:
            continue

        total_subidos = len(docs)
        total_req = len(req_tipos)

        last_update = None
        for d in docs:
            if d.actualizado_en and (last_update is None or d.actualizado_en > last_update):
                last_update = d.actualizado_en
        if last_update is None:
            last_update = a.actualizado_en

        items.append(
            {
                "alumno": a,
                "documentos": docs,
                "total_subidos": total_subidos,
                "total_requeridos": total_req,
                "faltantes": faltantes,
                "ultima_actualizacion": last_update,
            }
        )

    ctx = {"q": q, "items": items, "solo_faltantes": solo_faltantes}  # << NUEVO en contexto
    return render(request, "alumnos/documentos_lista.html", ctx)

###############################################################
@login_required
def config_panel(request):
    return render(request, "panel/panel-configuracion.html")
###############################################################

from decimal import Decimal
from django.db import transaction
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.contrib import messages
from django.contrib.auth.decorators import login_required

from .models import Cargo, ClipPaymentOrder, Pago
from .clip_api import ClipClient

@login_required
def crear_pago_de_cargo(request, cargo_id):
    # 1) Obtener el cargo + alumno
    cargo = get_object_or_404(
        Cargo.objects.select_related("alumno", "concepto"),
        pk=cargo_id
    )
    alumno = cargo.alumno
    if not alumno:
        return HttpResponseBadRequest("El cargo no tiene alumno asignado.")

    # 2) Monto y descripción (evita guiones raros; el cliente vuelve a sanear)
    amount = cargo.monto.quantize(Decimal("0.01"))
    description = f"{cargo.concepto.nombre} - Alumno {alumno.numero_estudiante}"

    # 3) Crear la orden local primero (para tener un ID de referencia)
    with transaction.atomic():
        orden = ClipPaymentOrder.objects.create(
            alumno=alumno,
            cargo=cargo,
            amount=amount,
            description=description,
            status="created",
        )

    # 4) URLs absolutas de retorno
    success_url = request.build_absolute_uri(reverse("clip_pago_exitoso", args=[orden.pk]))
    cancel_url  = request.build_absolute_uri(reverse("clip_pago_cancelado", args=[orden.pk]))

    # 5) Llamar a Clip (el cliente manda centavos y usa 'reference' internamente)
    client = ClipClient()
    data, code = client.create_payment_link(
        amount=float(amount),
        description=description,
        order_id=str(orden.pk),     # map a 'reference' dentro del cliente
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={
            "alumno_id": alumno.pk,
            "cargo_id": cargo.pk,
            "numero_estudiante": alumno.numero_estudiante,
        },
        description_max_len=50,     # seguro para la validación de descripción
        # use_cents=True ya es el default en tu cliente
    )

    # 6) Persistir request/response para auditoría
    orden.raw_request = {
        "amount": str(amount),
        "description": description,
        "order_id": str(orden.pk),
        "success_url": success_url,
        "cancel_url": cancel_url,
        "metadata": {
            "alumno_id": alumno.pk,
            "cargo_id": cargo.pk,
            "numero_estudiante": alumno.numero_estudiante,
        }
    }
    orden.raw_response = data

    # 7) Extraer datos devueltos por Clip
    orden.clip_payment_id = str(data.get("id") or data.get("payment_id") or "")
    orden.checkout_url = str(
        data.get("checkout_url")
        or data.get("url")
        or data.get("redirect_url")
        or data.get("payment_url")
        or ""
    )

    # 8) Estado local
    orden.status = "pending" if (code and 200 <= code < 300 and orden.checkout_url) else "failed"
    orden.save(update_fields=["raw_request", "raw_response", "clip_payment_id", "checkout_url", "status"])

    # 9) Manejo de error visible y depurable
    if not orden.checkout_url:
        msg = data.get("message") or data.get("error") or "No se pudo crear el pago."
        detail = data.get("detail") or data.get("_raw_text") or data.get("_content_type") or ""
        messages.error(request, f"Error al crear el pago ({code}): {msg}. {detail}")
        return render(
            request,
            "pagos/crear_error.html",
            {"orden": orden, "mensaje": msg, "respuesta": data, "status_code": code},
        )

    # 10) Redirigir al checkout
    return redirect(orden.checkout_url)


@login_required
def pago_exitoso(request, orden_id):
    orden = get_object_or_404(ClipPaymentOrder, pk=orden_id)
    return render(request, "pagos/exito.html", {"orden": orden})


@login_required
def pago_cancelado(request, orden_id):
    orden = get_object_or_404(ClipPaymentOrder, pk=orden_id)
    return render(request, "pagos/cancelado.html", {"orden": orden})


from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse, HttpResponse, HttpResponseBadRequest
from django.urls import reverse
from django.db import transaction
from decimal import Decimal


from .clip_api import ClipClient, verify_webhook_signature
from .utils import get_active_clip_credential

@csrf_exempt
def clip_webhook(request):
    raw = request.body
    sig = request.headers.get("X-Clip-Signature", "")  # ajusta si tu cuenta usa otro nombre

    cred = get_active_clip_credential()
    if not verify_webhook_signature(cred.secret_key or "", raw, sig):
        return HttpResponse(status=400)

    try:
        data = json.loads(raw.decode("utf-8"))
    except Exception:
        return HttpResponseBadRequest("Payload inválido")

    event_type = data.get("type") or data.get("event") or ""
    payment_obj = data.get("data") or data.get("payment") or {}
    clip_payment_id = str(payment_obj.get("id") or payment_obj.get("payment_id") or "")
    ref = str(payment_obj.get("reference") or "")
    status = str(payment_obj.get("status") or "").lower()

    orden = (ClipPaymentOrder.objects
             .filter(clip_payment_id=clip_payment_id)
             .first()) or (ClipPaymentOrder.objects.filter(pk=ref).first())

    if not orden:
        return HttpResponse(status=200)

    orden.last_webhook = data

    if status in ("succeeded", "paid", "completed"):
        with transaction.atomic():
            orden.status = "paid"
            orden.save(update_fields=["status", "last_webhook", "updated_at"])

            if orden.cargo and not orden.cargo.pagado:
                Pago.objects.create(
                    alumno=orden.alumno,
                    fecha=timezone.now().date(),
                    monto=orden.amount,
                    metodo="Tarjeta (Clip)",
                    banco="",
                    referencia=orden.clip_payment_id or ref,
                    descripcion=orden.description,
                    conciliado=True,
                    cargo=orden.cargo,
                )
                orden.cargo.pagado = True
                orden.cargo.save(update_fields=["pagado"])
    elif status in ("canceled", "failed", "expired"):
        orden.status = status
        orden.save(update_fields=["status", "last_webhook", "updated_at"])

    return HttpResponse(status=200)
################################################################
from .utils import send_sms, send_whatsapp
@login_required
def enviar_sms(request):
    to = request.GET.get("to")  # '+52...'
    if not to:
        return HttpResponseBadRequest("Falta parámetro to")
    callback = request.build_absolute_uri(reverse("twilio_status_callback"))
    # Si quieres forzar entorno: env="sandbox" o "prod"
    m = send_sms(to, "Hola desde Twilio SMS 🚀", env=None, status_callback=callback)
    return JsonResponse({"sid": m.sid, "status": m.status})

@login_required
def enviar_wa(request):
    to = request.GET.get("to")
    if not to:
        return HttpResponseBadRequest("Falta parámetro to")
    callback = request.build_absolute_uri(reverse("twilio_status_callback"))
    m = send_whatsapp(to, "Hola por WhatsApp 👋", env=None, status_callback=callback)
    return JsonResponse({"sid": m.sid, "status": m.status})

@csrf_exempt
def twilio_status_callback(request):
    """
    Twilio enviará POST con campos como:
    MessageSid, SmsStatus (queued/sent/delivered/undelivered/failed), To, From, ErrorCode, ErrorMessage, etc.
    """
    if request.method != "POST":
        return HttpResponse(status=405)

    # Lee tanto form-encoded como JSON
    payload = request.POST.dict()
    if not payload:
        try:
            payload = json.loads(request.body.decode("utf-8"))
        except Exception:
            payload = {}

    # TODO: aquí persiste en BD si quieres loguear estados
    # Twilio recomienda responder 200 OK rápido
    return JsonResponse({"ok": True})

###############################################################
# alumnos/views.py
from alumnos.utils import documentos_a_pdf

# views.py (o utils.py según prefieras)
from io import BytesIO
import os

from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404
from django.db.models import Q, Max

from pypdf import PdfWriter, PdfReader
from PIL import Image

from alumnos.models import Alumno, DocumentoAlumno, DocumentoTipo, ProgramaDocumentoRequisito
from alumnos.permisos import user_can_view_documentos  # ajusta si tu helper se llama distinto


IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".gif", ".webp"}


def _image_file_to_pdf_bytes(django_file) -> BytesIO:
    """
    Convierte una imagen (subida) a un PDF monoplano en memoria.
    Retorna un BytesIO posicionado al inicio.
    """
    django_file.open("rb")
    try:
        img = Image.open(django_file)
        # Asegurar modo compatible
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        out = BytesIO()
        img.save(out, format="PDF")
        out.seek(0)
        return out
    finally:
        try:
            django_file.close()
        except Exception:
            pass


def documentos_a_pdf_dinamico(*, info_escolar=None, documentos_qs=None, titulo="Documentos del alumno") -> bytes:
    """
    Une todos los archivos de DocumentoAlumno en un solo PDF.
    - PDFs se agregan tal cual (todas sus páginas)
    - Imágenes se convierten a PDF y se agregan
    - Ignora tipos sin archivo
    Puedes pasar:
      - info_escolar=<InformacionEscolar>  (usará sus DocumentoAlumno)
      - documentos_qs=<QuerySet de DocumentoAlumno>
    """
    if documentos_qs is None:
        if info_escolar is None:
            raise ValueError("Debes proveer info_escolar o documentos_qs.")
        documentos_qs = DocumentoAlumno.objects.filter(info_escolar=info_escolar)

    # Orden recomendado:
    # 1) Si hay requisitos configurados para el programa, priorizamos ese orden (si existe un campo 'orden')
    # 2) Luego por nombre de tipo
    # 3) Finalmente por fecha de actualización
    # Nota: si tu ProgramaDocumentoRequisito no tiene campo 'orden', este bloque simplemente
    # termina ordenando por tipo__nombre y actualizado_en.
    if info_escolar and getattr(info_escolar, "programa_id", None):
        reqs = ProgramaDocumentoRequisito.objects.filter(
            programa=info_escolar.programa, activo=True, tipo__activo=True
        ).select_related("tipo")
        # Si manejas requisitos por nacionalidad, puedes filtrar aquí como en tus otras vistas.

        # Mapa tipo_id -> índice de prioridad por requisito (si no hay 'orden', usamos enumeración)
        prioridad = {}
        for idx, r in enumerate(reqs.order_by("orden" if hasattr(reqs.model, "orden") else "id")):
            prioridad[r.tipo_id] = idx

        documentos = list(
            documentos_qs.select_related("tipo")
                         .order_by("tipo__nombre", "-actualizado_en", "-id")
        )
        # Reordena por prioridad primero (si existe el tipo en el mapa)
        documentos.sort(key=lambda d: (prioridad.get(d.tipo_id, 10_000), d.tipo.nombre.lower()))
    else:
        documentos = list(
            documentos_qs.select_related("tipo")
                         .order_by("tipo__nombre", "-actualizado_en", "-id")
        )

    writer = PdfWriter()

    for d in documentos:
        f = d.archivo
        if not f:
            continue
        _, ext = os.path.splitext(f.name or "")
        ext = ext.lower()

        try:
            if ext == ".pdf":
                f.open("rb")
                reader = PdfReader(f)
                for page in reader.pages:
                    writer.add_page(page)
            elif ext in IMAGE_EXTS:
                img_pdf = _image_file_to_pdf_bytes(f)  # BytesIO
                reader = PdfReader(img_pdf)
                for page in reader.pages:
                    writer.add_page(page)
            else:
                # Extensión no soportada: lo ignoramos (o podrías agregar una hoja separadora con ReportLab).
                continue
        finally:
            try:
                f.close()
            except Exception:
                pass

    # Metadatos del PDF
    writer.add_metadata({
        "/Title": titulo,
        "/Author": "CampusIUAF",
    })

    out = BytesIO()

    # Si no hay páginas, devolvemos un PDF con una sola página informativa
    

    if len(writer.pages) == 0:
        
        buf = BytesIO()
        c = canvas.Canvas(buf, pagesize=A4)
        c.setFont("Helvetica", 12)
        c.drawString(72, 800, "No hay documentos para mostrar.")

        # --- Imagen estática de pie de página (cámbiala cuando quieras) ---
        left_margin = 40
        right_margin = 40
        bottom_margin = 16

        from django.contrib.staticfiles import finders
        footer_img_path = finders.find("recibos/footer.png")  # ← tu subcarpeta/archivo

        #footer_img_path = os.path.join(settings.BASE_DIR, "static", "recibos", "footer.png")
        # Ejemplo alterno: footer_img_path = r"C:\ruta\a\tu\imagen\footer.png"
        from alumnos.utils import draw_fullwidth_image_bottom

        draw_fullwidth_image_bottom(c, W, left_margin, right_margin, bottom_margin, footer_img_path)


        c.showPage()
        c.save()
        buf.seek(0)
        reader = PdfReader(buf)
        for page in reader.pages:
            writer.add_page(page)

    writer.write(out)
    out.seek(0)
    return out.read()


@login_required
def documentos_unificados_pdf(request, alumno_id):
    """
    Devuelve un PDF con TODOS los documentos del alumno (esquema dinámico).
    """
    alumno = get_object_or_404(Alumno, pk=alumno_id)

    # Permisos
    if not user_can_view_documentos(request.user):
        return HttpResponseForbidden("No tienes permiso para ver/descargar documentos.")

    info = getattr(alumno, "informacionEscolar", None)
    if not info:
        raise Http404("El alumno no tiene un plan escolar asignado.")

    pdf_bytes = documentos_a_pdf_dinamico(
        info_escolar=info,
        titulo=f"Documentos — {alumno.numero_estudiante or alumno.pk}",
    )

    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="documentos_alumno_{alumno_id}.pdf"'
    return response

################################################################
from django.contrib.admin.views.decorators import staff_member_required
from django.views.decorators.http import require_http_methods
from django.core.management import call_command
import io
from pathlib import Path
# Si vas a guardar en DB:
from alumnos.services.movimientos_loader import upsert_movimientos

@staff_member_required
@require_http_methods(["GET", "POST"])
def run_leer_google_sheet(request):
    """
    Muestra un botón y, al hacer POST, ejecuta el management command
    leer_google_sheet con los defaults (Sheet ID / hoja "2022" puestos en el comando).
    Opcional: guarda los movimientos en DB leyendo el JSON resultante.
    """
    context = {}
    if request.method == "POST":
        # 1) Ruta de salida (carpeta del proyecto /salidas/)
        out_path = Path("salidas/movimientos_2022.json")
        out_path.parent.mkdir(parents=True, exist_ok=True)

        # 2) Buffers para capturar salida del comando (útil en debug)
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()

        # 3) Flags
        save_db = request.POST.get("save_db") == "1"  # pon un input hidden si quieres activar esto desde el template

        try:
            # 4) Ejecutar management command
            call_command(
                "leer_google_sheet",
                "--por", "nombre",
                "--out-json", str(out_path),
                "--debug",            # quítalo si no quieres verbosidad
                stdout=stdout_buf,
                stderr=stderr_buf,
            )

            messages.success(request, f"¡Listo! JSON guardado en: {out_path}")
            context["output"] = stdout_buf.getvalue()

            # 5) Si se solicita, cargar el JSON y guardar en DB (upsert)
            if save_db:
                try:
                    data = json.loads(out_path.read_text(encoding="utf-8"))
                except Exception as e_json:
                    messages.error(request, f"No pude leer el JSON de salida ({out_path}): {e_json}")
                else:
                    try:
                        res = upsert_movimientos(
                            data,
                            source_sheet_id="1G0P64LVOfxG4siNXmTm0gCORoaPby2W2_wu0Z869Dvk",
                            source_sheet_name="2022",
                            source_gid="1206699819",
                        )
                        messages.success(
                            request,
                            f"DB → creados {res['created']}, actualizados {res['updated']}."
                        )
                    except Exception as e_db:
                        messages.error(request, f"Error guardando en DB: {e_db}")

        except Exception as e:
            # Si el call_command truena, mostramos stderr + excepción
            err = stderr_buf.getvalue()
            messages.error(request, f"Error al ejecutar el comando: {e}")
            context["output"] = f"{err}\n{e}"

    return render(request, "alumnos/run_leer_google_sheet.html", context)


################################################################
from .models import MovimientoBanco 

@method_decorator(login_required, name="dispatch")
class MovimientoBancoListView(ListView):
    model = MovimientoBanco
    template_name = "panel/movimientos_list.html"
    context_object_name = "movimientos"
    paginate_by = None

    def get_queryset(self):
        user = self.request.user

        if (not user.is_authenticated) or (not user.is_superuser and not user.groups.filter(name="pagos").exists()):
            return MovimientoBanco.objects.none()

        qs = MovimientoBanco.objects.all().order_by("id")

        signo = self.request.GET.get("signo")
        tipo  = self.request.GET.get("tipo")
        fmin  = self.request.GET.get("desde")
        fmax  = self.request.GET.get("hasta")

        if signo in ("1", "-1"):
            qs = qs.filter(signo=int(signo))
        if tipo:
            qs = qs.filter(tipo__icontains=tipo)
        if fmin:
            qs = qs.filter(fecha__gte=fmin)
        if fmax:
            qs = qs.filter(fecha__lte=fmax)

        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        qs = self.object_list

        user = self.request.user
        ctx["total_registros"] = qs.count()
        ctx["total_abonos"] = qs.filter(signo=1).aggregate(s=Sum("monto"))["s"] or Decimal("0")
        ctx["total_cargos"] = qs.filter(signo=-1).aggregate(s=Sum("monto"))["s"] or Decimal("0")

        # 🔸 Añadimos banderas de permisos por grupo
        ctx["puede_conciliar"] = (
            user.is_superuser or user.groups.filter(name="Conciliadores Bancarios").exists()
        )
        ctx["puede_deshacer"] = (
            user.is_superuser or user.groups.filter(name="Supervisores Bancarios").exists()
        )

        return ctx


###############################################################
SHEET_ID = "1G0P64LVOfxG4siNXmTm0gCORoaPby2W2_wu0Z869Dvk"
SHEET_NAME = "2022"
SHEET_GID = "1206699819"

@staff_member_required
@require_POST
def run_movimientos_banco_update(request):
    """
    Ejecuta el comando que lee el Google Sheet (hoja '2022'),
    guarda un JSON y luego hace upsert en DB.
    No renderiza salida; solo mensajes y redirige al listado.
    """
    out_path = Path("salidas/movimientos_2022.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()

    try:
        # 1) Ejecutar el management command que genera el JSON
        call_command(
            "leer_google_sheet",
            "--por", "nombre",
            "--out-json", str(out_path),
            # sin --debug para no llenar buffers (aun así capturamos por si hay error)
            stdout=stdout_buf,
            stderr=stderr_buf,
        )

        # 2) Cargar JSON
        try:
            data = json.loads(out_path.read_text(encoding="utf-8"))
        except Exception as e_json:
            messages.error(request, f"No pude leer el JSON ({out_path}): {e_json}")
            return redirect("movimientos_banco_lista")

        # 3) Guardar/actualizar en DB
        try:
            res = upsert_movimientos(
                data,
                source_sheet_id=SHEET_ID,
                source_sheet_name=SHEET_NAME,
                source_gid=SHEET_GID,
            )
            created = res.get("created", 0)
            updated = res.get("updated", 0)
            messages.success(request, f"Movimientos actualizados. Creados: {created} · Actualizados: {updated}.")
        except Exception as e_db:
            messages.error(request, f"Error guardando en BD: {e_db}")

    except Exception as e_cmd:
        # Si el comando falla, mostramos su stderr resumido
        err = stderr_buf.getvalue().strip()
        if err:
            messages.error(request, f"Error al ejecutar importación: {e_cmd}. Detalle: {err[:500]}")
        else:
            messages.error(request, f"Error al ejecutar importación: {e_cmd}")

    return redirect("movimientos_banco_lista")    

###########################################################################################
from django.views.decorators.csrf import csrf_protect
from .models import UploadInvite

@csrf_protect
def public_upload(request, token):
    invite = get_object_or_404(UploadInvite, token=token)

    # Flags útiles para la UI (tu template los puede usar)
    invite_is_expired = not invite.is_valid()
    invite_is_revoked = bool(getattr(invite, "revoked", False))

    if invite_is_expired:
        return render(
            request,
            "alumnos/public_upload_invalid.html",
            {"invite": invite},
            status=410,
        )

    alumno = invite.alumno
    info = getattr(alumno, "informacionEscolar", None)

    # -------------------- DOCUMENTOS DEL ALUMNO --------------------
    uploads = (
        DocumentoAlumno.objects
        .filter(info_escolar__alumno=alumno)
        .select_related("tipo")
        .order_by("-actualizado_en", "-creado_en")
    )

    # -------------------- REQUISITOS / FALTANTES --------------------
    faltantes = []
    faltantes_ids = []
    faltantes_count = 0

    if info and getattr(info, "programa_id", None):
        reqs_qs = (
            ProgramaDocumentoRequisito.objects
            .filter(programa=info.programa, activo=True, tipo__activo=True)
            .select_related("tipo")
        )

        # Si manejas requisitos por nacionalidad, descomenta este bloque:
        # if _es_extranjero(info):
        #     reqs_qs = reqs_qs.filter(Q(aplica_a="todos") | Q(aplica_a="solo_extranjeros"))
        # else:
        #     reqs_qs = reqs_qs.filter(Q(aplica_a="todos") | Q(aplica_a="solo_nacionales"))

        tipos_requeridos = [r.tipo for r in reqs_qs]
        subidos_tipo_ids = {d.tipo_id for d in uploads if d.tipo_id}
        faltantes = [t for t in tipos_requeridos if t.id not in subidos_tipo_ids]
        faltantes_ids = [t.id for t in faltantes]
        faltantes_count = len(faltantes)

    # -------------------- ACCIÓN: ELIMINAR DOCUMENTO --------------------
    if request.method == "POST" and "delete" in request.POST:
        doc_id = request.POST.get("doc_id")
        doc = get_object_or_404(
            DocumentoAlumno,
            pk=doc_id,
            info_escolar__alumno=alumno  # seguridad: solo documentos del mismo alumno
        )
        if doc.valido is True:
            messages.error(request, "No puedes eliminar un documento marcado como válido.")
        else:
            # (Opcional) eliminar el archivo físico del storage
            archivo = doc.archivo
            doc.delete()
            try:
                if archivo and archivo.name:
                    archivo.storage.delete(archivo.name)
            except Exception:
                pass
            messages.success(request, "Documento eliminado.")
        return redirect("public_upload", token=invite.token)

    # -------------------- SUBIDA NORMAL --------------------
    if request.method == "POST" and "delete" not in request.POST:
        form = DocumentoAlumnoCreateForm(
            request.POST, request.FILES,
            info_escolar=getattr(alumno, "informacionEscolar", None),
        )
        # Restringir el select a faltantes (si hay)
        if faltantes_ids:
            form.fields["tipo"].queryset = DocumentoTipo.objects.filter(id__in=faltantes_ids).order_by("nombre")

        if form.is_valid():
            doc = form.save(commit=False)
            doc.info_escolar = getattr(alumno, "informacionEscolar", None)
            doc.save()

            invite.uses += 1
            invite.save(update_fields=["uses"])

            messages.success(request, "¡Documento subido correctamente!")
            return redirect("public_upload", token=invite.token)
        else:
            messages.error(request, "Revisa los campos del formulario.")
    else:
        form = DocumentoAlumnoCreateForm(
            info_escolar=getattr(alumno, "informacionEscolar", None)
        )
        if faltantes_ids:
            form.fields["tipo"].queryset = DocumentoTipo.objects.filter(id__in=faltantes_ids).order_by("nombre")

    # -------------------- RENDER --------------------
    return render(
        request,
        "alumnos/public_upload.html",
        {
            "alumno": alumno,
            "form": form,
            "invite": invite,
            "invite_is_expired": invite_is_expired,
            "invite_is_revoked": invite_is_revoked,
            "uploads": uploads,               # lista para la tabla
            "docs": uploads,                  # si tu template usa 'docs', dejamos alias
            "faltantes": faltantes,           # lista de DocumentoTipo faltantes
            "faltantes_count": faltantes_count,
        },
    )

@login_required
def crear_enlace_subida(request, pk):
    alumno = get_object_or_404(Alumno, pk=pk)
    expires = timezone.now() + timezone.timedelta(days=7)  # 7 días
    invite = UploadInvite.objects.create(
        alumno=alumno,
        expires_at=expires,
        max_uses=0,            # ilimitado hasta caducar (o pon 5, 10…)
        created_by=request.user,
    )
    url = request.build_absolute_uri(
        reverse("public_upload", args=[invite.token])
    )
    messages.success(request, f"Enlace generado: {url}")
    return redirect("alumnos_detalle", pk=alumno.pk)

def generar_enlace_subida(request, pk):
    alumno = get_object_or_404(Alumno, pk=pk)
    expires = timezone.now() + timezone.timedelta(days=7)  # dura 7 días
    invite = UploadInvite.objects.create(
        alumno=alumno,
        expires_at=expires,
        max_uses=0,  # ilimitado hasta expirar
        created_by=request.user if request.user.is_authenticated else None,
    )
    link = request.build_absolute_uri(
        reverse("public_upload", args=[invite.token])
    )
    messages.success(request, f"Enlace generado: {link}")
    return redirect("alumnos_documentos_editar", pk=alumno.pk)
################################################################
@require_POST
@login_required
def generar_enlace_subida_json(request, pk):
    """
    Crea un invite y devuelve el URL absoluto en JSON, ideal para AJAX.
    """
    alumno = get_object_or_404(Alumno, pk=pk)
    expires = timezone.now() + timezone.timedelta(days=7)
    invite = UploadInvite.objects.create(
        alumno=alumno,
        expires_at=expires,
        max_uses=0,
        created_by=request.user,
    )
    url = request.build_absolute_uri(reverse("public_upload", args=[invite.token]))
    return JsonResponse({"ok": True, "url": url, "expires_at": expires.isoformat()})

################################################################
from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import get_object_or_404, render, redirect
from django.utils import timezone
from django.contrib import messages
from django.db import transaction
from django.urls import reverse

from alumnos.models import MovimientoBanco, PagoDiario, Alumno
from alumnos.services.match_helpers import buscar_alumnos_candidatos

def puede_conciliar(u):
    return u.is_authenticated and (u.is_superuser or u.groups.filter(name='pagos').exists())

@login_required
@user_passes_test(puede_conciliar)
def movimientos_abonos_pendientes(request):
    q = (request.GET.get("q") or "").strip()
    qs = MovimientoBanco.objects.filter(signo=1, conciliado=False).order_by('id')
    if q:
        qs = qs.filter(
            Q(emisor_nombre__icontains=q) |
            Q(referencia_alfanumerica__icontains=q) |
            Q(concepto__icontains=q) |
            Q(referencia_numerica__icontains=q) |
            Q(autorizacion__icontains=q)
        )
    return render(request, "pagos/abonos_pendientes.html", {"movs": qs, "q": q})



###############################################################################
from  .models import ConceptoPago
def get_programa_text(alumno):
    """Devuelve texto legible del programa del alumno (string o FK)."""
    prog = getattr(alumno, "programa", None)
    if prog is None:
        return None
    if isinstance(prog, str):
        return prog.strip() or None
    for attr in ("nombre", "codigo", "clave", "descripcion"):
        val = getattr(prog, attr, None)
        if val:
            return str(val)
    return str(prog)

def get_sede_text(alumno):
    """Devuelve texto legible de la sede/cede del alumno (string o FK)."""
    for attr_name in ("sede", "cede"):
        val = getattr(alumno, attr_name, None)
        if val is None:
            continue
        if isinstance(val, str):
            return val.strip() or None
        for attr in ("nombre", "codigo", "clave", "descripcion"):
            v2 = getattr(val, attr, None)
            if v2:
                return str(v2)
        return str(val)
    return None

######################################
from django.forms import formset_factory
class LineaConciliacionForm(forms.Form):
    alumno_id   = forms.IntegerField(min_value=1, required=True)
    concepto_id = forms.IntegerField(min_value=1, required=True)
    monto       = forms.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))

    def clean_alumno_id(self):
        from .models import Alumno
        pk = self.cleaned_data["alumno_id"]
        if not Alumno.objects.filter(pk=pk).exists():
            raise forms.ValidationError("Alumno inválido.")
        return pk

    def clean_concepto_id(self):
        from .models import ConceptoPago
        pk = self.cleaned_data["concepto_id"]
        if not ConceptoPago.objects.filter(pk=pk).exists():
            raise forms.ValidationError("Concepto inválido.")
        return pk


LineaFormSet = formset_factory(LineaConciliacionForm, extra=1, can_delete=True)


from decimal import Decimal, ROUND_HALF_UP

def _q2(v):
    return (Decimal(v or 0).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))



@login_required
@user_passes_test(puede_conciliar)
def conciliar_movimiento(request, mov_id):
    mov = get_object_or_404(MovimientoBanco, pk=mov_id)

    base = (
        mov.nombre_detectado_save
        or mov.nombre_detectado
        or mov.emisor_nombre
        or mov.referencia_alfanumerica
        or ""
    )

    conceptos = ConceptoPago.objects.all().order_by("nombre")
    candidatos = buscar_alumnos_candidatos(base)

    if request.method == "POST":
        nds_input = (request.POST.get("nombre_detectado_save") or "").strip() or None
        formset = LineaFormSet(request.POST, prefix="lineas")

        if not formset.is_valid():
            print("❌ Formset inválido:", formset.errors)
            messages.error(request, "Revisa las líneas: hay errores en los datos.")
            return render(request, "pagos/conciliar_movimiento.html", {
                "mov": mov, "conceptos": conceptos, "candidatos": candidatos,
                "base": base, "formset": formset,
            })

        total = Decimal("0.00")
        lineas_validas = []
        for f in formset:
            if getattr(f, "cleaned_data", None) and not f.cleaned_data.get("DELETE", False):
                total += f.cleaned_data["monto"]
                lineas_validas.append(f.cleaned_data)

        total_norm = _q2(total)
        mov_norm   = _q2(mov.monto)

        if total_norm != mov_norm:
            messages.error(request, f"La suma de montos ({total_norm}) debe ser igual al monto del movimiento ({mov_norm}).")
            return render(request, "pagos/conciliar_movimiento.html", {
                "mov": mov, "conceptos": conceptos, "candidatos": candidatos,
                "base": base, "formset": formset,
            })

        try:
            with transaction.atomic():
                for data in lineas_validas:
                    alumno   = Alumno.objects.get(pk=data["alumno_id"])
                    concepto = ConceptoPago.objects.get(pk=data["concepto_id"])

                    programa_txt = get_programa_text(alumno)
                    sede_txt     = get_sede_text(alumno)

                    PagoDiario.objects.create(
                        # movimiento=mov,  # Descomenta si tu modelo PagoDiario tiene este FK
                        alumno=alumno,
                        fecha=mov.fecha,
                        monto=_q2(data["monto"]),
                        forma_pago="Transferencia/Depósito",
                        concepto=concepto.codigo,
                        pago_detalle=(mov.concepto or "")[:200],
                        folio=(mov.autorizacion or mov.referencia_numerica or "")[:32],
                        curp=alumno.curp or None,
                        numero_alumno=alumno.numero_estudiante,
                        nombre=f"{alumno.nombre} {alumno.apellido_p} {alumno.apellido_m}".strip(),
                        programa=alumno.informacionEscolar,
                        sede=alumno.informacionEscolar.sede,
                    )

                mov.nombre_detectado_save = nds_input
                mov.conciliado = True
                mov.conciliado_por = request.user
                mov.conciliado_en = timezone.now()
                mov.save(update_fields=["nombre_detectado_save","conciliado","conciliado_por","conciliado_en"])

            messages.success(request, f"✅ Conciliado. Se generaron {len(lineas_validas)} pagos.")
            return redirect(reverse("movimientos_abonos_pendientes"))

        except Exception as e:
            print("❌ Error al conciliar:", e)
            messages.error(request, f"Error al conciliar: {e}")

    else:
        formset = LineaFormSet(initial=[{"monto": mov.monto}], prefix="lineas")

    return render(request, "pagos/conciliar_movimiento.html", {
        "mov": mov, "conceptos": conceptos, "candidatos": candidatos,
        "base": base, "formset": formset,
    })

#############################################################################################
@login_required
@user_passes_test(puede_conciliar)
@require_POST
def set_nombre_detectado_save(request, pk):
    """Actualiza por AJAX el nombre_detectado_save de un MovimientoBanco."""
    mov = get_object_or_404(MovimientoBanco, pk=pk)

    # Obtén valor desde JSON o form-encoded
    value = request.POST.get("value")
    if value is None:
        try:
            import json
            data = json.loads(request.body.decode("utf-8") or "{}")
            value = data.get("value")
        except Exception:
            value = None

    # Normaliza un poco
    if value is not None:
        value = (value or "").strip()
        if not value:
            value = None

    # Valida longitud (tu modelo max_length=200)
    if value and len(value) > 200:
        return JsonResponse(
            {"ok": False, "error": "El nombre no puede exceder 200 caracteres."},
            status=400,
        )

    mov.nombre_detectado_save = value
    mov.save(update_fields=["nombre_detectado_save", "updated_at"])

    return JsonResponse({"ok": True, "value": mov.nombre_detectado_save})

############################################################################
@login_required
def deshacer_conciliacion(request, mov_id):
    mov = get_object_or_404(MovimientoBanco, pk=mov_id)
    ok, msg = mov.deshacer_conciliacion()
    messages.success(request, msg) if ok else messages.warning(request, msg)
    return redirect("movimientos_abonos_pendientes")


###########################################################################################
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.http import HttpResponse
from django.utils import timezone


# Evitar que WeasyPrint tumbe el server si no están sus DLLs en Windows
WEASYPRINT_OK = False
WEASYPRINT_ERR = None
try:
    from weasyprint import HTML, CSS
    WEASYPRINT_OK = True
except Exception as e:
    WEASYPRINT_ERR = e


from .models import PagoDiario
from django.conf import settings

try:
    from num2words import num2words  # pip install num2words
except Exception:
    num2words = None

from reportlab.pdfgen import canvas as rl_canvas

@login_required
def pago_recibo_pdf(request, pk):
    # --- Imports locales para ser auto-contenidos ---
    from io import BytesIO
    from reportlab.pdfgen import canvas as rl_canvas
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.pdfbase.pdfmetrics import stringWidth

    def is_overdue(pago, today):
        """
        Determina si el pago es extemporáneo.
        1) Boolean directo: pago.es_estemporaneo
        2) Por fecha de vencimiento: (pago.fecha or hoy) > pago.fecha_vencimiento
        3) Por estado textual: 'extemporaneo'/'extemporáneo'/similar
        """
        val = getattr(pago, "es_estemporaneo", None)
        if val is not None:
            return bool(val)
        fv = getattr(pago, "fecha_vencimiento", None)
        if fv:
            fecha_base = getattr(pago, "fecha", None) or today
            try:
                return fecha_base > fv
            except Exception:
                pass
        estado = str(getattr(pago, "estado", "")).strip().lower()
        return estado in {"extemporaneo", "extemporáneo", "atrasado", "tarde"}

    def draw_badge_right(c, page_width, y, text, bg_color,
                         font_name="Helvetica-Bold", font_size=10, pad_x=3, pad_y=8, radius=3):
        """
        Dibuja una 'pastilla' alineada a la derecha con fondo de color y texto en blanco.
        """
        c.setFont(font_name, font_size)
        tw = stringWidth(text, font_name, font_size)
        rect_w = tw + pad_x * 2
        rect_h = font_size + pad_y * 2

        x = page_width - 40 - rect_w  # margen derecho de 40
        # rectángulo redondeado (fallback a rect si no hay roundRect)
        c.setFillColor(bg_color)
        c.setStrokeColor(bg_color)
        try:
            c.roundRect(x, y - rect_h + 2, rect_w, rect_h, radius, fill=1, stroke=0)
        except Exception:
            c.rect(x, y - rect_h + 2, rect_w, rect_h, fill=1, stroke=0)

        # texto
        c.setFillColor(colors.white)
        c.drawString(x + pad_x, y - rect_h + pad_y + font_size * 0.2, text)
        c.setFillColor(colors.black)

    from .models import PagoDiario

    pago = get_object_or_404(
        PagoDiario.objects.select_related("alumno"),
        pk=pk
    )
    alumno = pago.alumno
    hoy = timezone.localdate()

    # Monto en letras (opcional)
    monto_letras = ""
    if num2words and pago.monto is not None:
        try:
            monto_letras = num2words(pago.monto, lang="es").upper()
        except Exception:
            monto_letras = ""

    ctx = {
        "pago": pago,
        "alumno": alumno,
        "hoy": hoy,
        "monto_letras": monto_letras,
        "institucion": {
            "nombre": "INSTITUTO UNIVERSITARIO DE ALTA FORMACIÓN IUAF SC.",
            "rfc": "R.F.C. IUAT0913LI2",
            "cct": "25PSU00064H",
            "ciudad": "Cancún Q. R.",
            "direccion": "BOULEVARD KUKULKAN M2.30 LTD.-9.8 KM 3.5 ZONA HOTELERA. CANCÚN Q. R. 9992636780",
        },
    }

    # === Opción A: usar WeasyPrint si está disponible ===
    if globals().get("WEASYPRINT_OK"):
        try:
            html = render_to_string("alumnos/recibo_pago.html", ctx)
            response = HttpResponse(content_type="application/pdf")
            filename = f"recibo_{pago.folio or pago.pk}.pdf"
            response["Content-Disposition"] = f'inline; filename="{filename}"'
            base_url = request.build_absolute_uri("/")
            # Nota: en tu template, usa {{ hoy|date:"d \\d\\e F \\d\\e Y" }} para evitar el error del 'e'
            HTML(string=html, base_url=base_url).write_pdf(
                response,
                stylesheets=[CSS(string="""
                    @page { size: A4; margin: 18mm 16mm 18mm 16mm; }
                    body { font-family: Arial, Helvetica, sans-serif; font-size: 12px; color:#111; }
                    .hdr { text-align:center; }
                    .hdr h1 { font-size: 16px; margin: 0 0 4px; }
                    .hdr .sub { font-size: 11px; color:#444; }
                    .grid { width:100%; border-collapse:collapse; }
                    .grid td { padding:6px 8px; vertical-align:top; }
                    .label { color:#555; width:30%; }
                    .box { border:1px solid #999; padding:8px; }
                    .title { letter-spacing:.35em; text-align:center; margin:10px 0 12px; }
                    .monto { font-size: 14px; font-weight:bold; }
                    .badge { background:#e6f4ea; border:1px solid #a8dab5; padding:6px 10px; display:inline-block; }
                    .footer { margin-top: 18px; font-size: 10px; color:#666; text-align:center; }
                    .row { display:flex; gap:12px; }
                    .col { flex:1; }
                    .right { text-align:right; }
                    .center { text-align:center; }
                    .muted { color:#666; }
                    .folio { background: #fff6a5; border:1px solid #e6d85a; padding:2px 8px; font-weight:bold; }
                """)]
            )
            return response
        except Exception as e:
            # Si falla WeasyPrint por DLLs u otra cosa, cae al fallback
            pass

    # === Opción B (fallback): generar PDF con ReportLab + badge ===
    buf = BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=A4)
    W, H = A4

    y = H - 50
    c.setFont("Helvetica-Bold", 14)
    c.drawCentredString(W/2, y, ctx["institucion"]["nombre"])
    y -= 16
    c.setFont("Helvetica", 10)
    c.drawCentredString(W/2, y, f"{ctx['institucion']['rfc']} • {ctx['institucion']['cct']}")
    y -= 14
    c.drawCentredString(W/2, y, f"{ctx['institucion']['ciudad']} — {hoy.strftime('%d de %B de %Y')}")

    y -= 28
    c.setFont("Helvetica-Bold", 12)
    c.drawCentredString(W/2, y, "R E C I B O   D E   P A G O")

    y -= 24
    c.setFont("Helvetica", 11)
    c.drawString(40, y, f"Folio: {pago.folio or pago.pk}")
    c.drawRightString(W-40, y, f"% BECA otorgado: "
                      f"{getattr(getattr(alumno.informacionEscolar, 'financiamiento', None), 'beca', '—')}")
    y -= 18
    c.drawString(40, y, f"Recibimos de: {alumno.nombre} {alumno.apellido_p} {alumno.apellido_m}")
    y -= 18
    c.drawString(40, y, f"CURP: {alumno.curp or '—'}")

    y -= 28
    c.setFont("Helvetica-Bold", 11)
    c.drawString(40, y, "La cantidad de:")
    c.setFont("Helvetica", 12)
    c.drawString(140, y, f"$ {pago.monto or '0.00'}")

    # --- Badge a la derecha ---
    overdue = is_overdue(pago, hoy)
    if overdue:
        draw_badge_right(c, W, y, "PAGO ESTEMPORÁNEO", colors.HexColor("#c62828"))
    else:
        draw_badge_right(c, W, y, "PAGO OPORTUNO", colors.HexColor("#4dad52"))

    if monto_letras:
        y -= 22
        c.setFont("Helvetica-Oblique", 10)
        c.drawCentredString(W/2, y, f"SON {monto_letras} 00/100 M.N.")

    y -= 26
    c.setFont("Helvetica", 10)
    prog = getattr(getattr(alumno, "informacionEscolar", None), "programa", None)
    sede = getattr(getattr(alumno, "informacionEscolar", None), "sede", None)
    c.drawString(40, y, f"Programa: {getattr(prog, 'nombre', '—')}")
    c.drawRightString(W-40, y, f"Sede: {sede or '—'}")
    y -= 18
    c.drawString(40, y, f"Concepto de pago: {pago.concepto or '—'}")
    y -= 18
    c.drawString(40, y, f"Detalle: {pago.pago_detalle or '—'}")
    y -= 18
    c.drawString(40, y, f"Forma de pago: {pago.forma_pago or '—'}")
    c.drawRightString(W-40, y, f"Fecha de pago: {pago.fecha.strftime('%d/%m/%Y') if pago.fecha else '—'}")

    y -= 30
    c.setFont("Helvetica", 9)
    c.drawCentredString(W/2, y, ctx["institucion"]["direccion"])

    c.showPage()
    c.save()
    pdf = buf.getvalue()
    buf.close()

    resp = HttpResponse(pdf, content_type="application/pdf")
    resp["Content-Disposition"] = f'inline; filename="recibo_{pago.folio or pago.pk}.pdf"'
    return resp