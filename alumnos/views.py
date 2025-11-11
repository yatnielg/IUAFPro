from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django import forms
from .models import Alumno, Programa
from django.contrib.auth.models import User, Group


try:
    from weasyprint import HTML
    _WEASY = True
except Exception:
    _WEASY = False

try:
    from xhtml2pdf import pisa
    _PISA = True
except Exception:
    _PISA = False




from playwright.sync_api import sync_playwright



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

from django.db.models import Q, Sum, Max
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
from django.views.decorators.http import require_GET
@login_required
@require_GET
def api_financiamientos_list(request):
    prog_id = request.GET.get("programa")
    qs = Financiamiento.objects.all()

    if prog_id and prog_id.isdigit():
        pid = int(prog_id)
        qs = qs.filter(Q(programa_id=pid) | Q(programa__isnull=True))
    else:
        # Sin programa seleccionado => solo globales
        qs = qs.filter(programa__isnull=True)

    items = []
    for f in qs.order_by("programa_id", "id"):
        label = f"{str(f)} (Global)" if f.programa_id is None else str(f)
        items.append({
            "id": f.id,
            "label": label,
            "is_global": f.programa_id is None,
        })

    return JsonResponse({"ok": True, "items": items})

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
        ).order_by("-numero_estudiante")  # 👈 forzar orden en Postgres
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
from academico.models import Calificacion

@login_required
def alumnos_detalle(request, pk):
    alumno = get_object_or_404(
        Alumno.objects.select_related(
            "pais", "estado", "informacionEscolar",
            "informacionEscolar__programa", "informacionEscolar__sede",
             "informacionEscolar__grupo_nuevo",  # 👈 AÑADIR
        ),
        pk=pk,
    )

    # -------- Permisos de visualización del alumno --------
    hoy = timezone.now().date()
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
    hay_cargos_vinculados = Cargo.objects.filter(alumno=alumno).exists()
    pagos = cargos = cargos_pendientes = None
    pagos_total = 0
    if can_view_pagos:
        pagos = (
            PagoDiario.objects
            .filter(alumno=alumno)
            .order_by("fecha", "-id")
        )
        pagos_total = round(pagos.aggregate(total=Sum("monto"))["total"] or 0, 2)

        pago_total_mayor_a_cero = True if pagos_total > 0 else False

        from django.db.models.functions import Coalesce
        cargos = (
            Cargo.objects
            .filter(
                alumno=alumno,
                pagado=False
            )
            # Mostrar los que ya están en fecha de pago (fecha_cargo ≤ hoy)
            # o que ya vencieron (fecha_vencimiento ≤ hoy).
            .filter(
                Q(fecha_cargo__lte=hoy) |
                Q(fecha_vencimiento__lte=hoy)
            )
            .annotate(
                # Fecha “exigible” solo para ordenar/mostrar
                due_date=Coalesce("fecha_vencimiento", "fecha_cargo"),
                # Vencido = si tiene fecha_vencimiento y es < hoy,
                # o si NO tiene fecha_vencimiento y la fecha_cargo es < hoy.
                is_overdue=Case(
                    When(Q(fecha_vencimiento__isnull=False) & Q(fecha_vencimiento__lt=hoy), then=Value(True)),
                    When(Q(fecha_vencimiento__isnull=True)  & Q(fecha_cargo__lt=hoy),         then=Value(True)),
                    default=Value(False),
                    output_field=BooleanField()
                )
            )
            .select_related("concepto")
            # Orden: primero vencidos, luego los “en fecha de pago” (hoy),
            # y dentro de cada grupo por due_date descendente.
            .order_by(
                # Vencidos arriba
                Case(
                    When(is_overdue=True, then=Value(0)),
                    default=Value(1),
                ),
                "-due_date",
                "-id",
            )
        )
        cargos_pendientes = cargos.filter(pagado=False)


    # === TAB 2: TODOS los cargos pendientes (vencidos, en fecha, y por pagar) ===
    from django.db.models.functions import Coalesce
    from django.db.models import IntegerField
    cargos_todos = (
        Cargo.objects
        .filter(alumno=alumno, pagado=False)
        .annotate(
            due_date=Coalesce("fecha_vencimiento", "fecha_cargo"),

            # VENCIDO
            is_overdue=Case(
                When(Q(fecha_vencimiento__isnull=False, fecha_vencimiento__lt=hoy), then=Value(True)),
                When(Q(fecha_vencimiento__isnull=True,  fecha_cargo__lt=hoy),        then=Value(True)),
                default=Value(False), output_field=BooleanField()
            ),

            # EN FECHA (ventana) => hoy entre fecha_cargo y fecha_vencimiento (incl.)
            # si no hay vencimiento, en fecha solo si hoy == fecha_cargo
            is_in_date_window=Case(
                When(Q(fecha_vencimiento__isnull=False, fecha_cargo__lte=hoy, fecha_vencimiento__gte=hoy), then=Value(True)),
                When(Q(fecha_vencimiento__isnull=True,  fecha_cargo=hoy),                                   then=Value(True)),
                default=Value(False), output_field=BooleanField()
            ),

            # Orden: Vencidos → En fecha → Por pagar
            status_order=Case(
                When(is_overdue=True,        then=Value(0)),
                When(is_in_date_window=True, then=Value(1)),
                default=Value(2),
                output_field=IntegerField(),
            ),
        )
        .select_related("concepto")
        .order_by("status_order", "due_date", "-id")
    )

    # -------- Documentos DINÁMICOS por programa --------
    docs = []
    docs_total = 0
    docs_last_update = None
    faltantes = []

    info = getattr(alumno, "informacionEscolar", None)
    prog = getattr(info, "programa", None)

    # <<< NUEVO: flag para “Fin del programa en futuro” >>>
# -------- Documentos / fin_programa --------
    fin_programa_is_future = False
    if info and getattr(info, "fin_programa", None):
        fin_programa_is_future = info.fin_programa > hoy

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

  
    # Si quieres permitir cambiar la regla de prioridad (?orden=antiguos)
    orden = request.GET.get('orden', 'recientes')
    restar_mas_recientes = (orden != 'antiguos')

    data = calcular_cargos_con_saldo(alumno, restar_pagos_mas_recientes=restar_mas_recientes)

    def anotar_flags(items):
        if not items:
            return
        for d in items:
            fv = d.get("fecha_vencimiento") or d.get("fecha_cargo")
            if d.get("monto_restante", 0) > 0 and fv:
                # solo si el helper no lo trae
                if "is_overdue" not in d:
                    d["is_overdue"] = (fv < hoy)
                if "is_due_today" not in d:
                    d["is_due_today"] = (fv == hoy)

    # --- Normaliza 'rows' a una lista y anota flags si faltan ---
    if isinstance(data, dict):
        # ajusta a la colección que usas en el template "Todos (pendientes)"
        rows = data.get("cargos_pendientes") or data.get("cargos_todos") or []
    else:
        rows = data or []

    for d in rows:
        fc = d.get("fecha_cargo")
        fv = d.get("fecha_vencimiento") or None
        if d.get("monto_restante", 0) > 0 and fc:
            # Vencido
            d.setdefault("is_overdue",
                        (fv is not None and fv < hoy) or (fv is None and fc < hoy))
            # En fecha (ventana)
            in_window = (
                (fv is not None and fc <= hoy <= fv) or
                (fv is None and fc == hoy)
            )
            d.setdefault("is_in_date_window", in_window)

    # Totales
    total_original = sum(d['monto_original'] for d in data) if data else 0
    total_aplicado = sum(d['monto_aplicado'] for d in data) if data else 0
    total_restante = sum(d['monto_restante'] for d in data) if data else 0


    califs = (
        Calificacion.objects
        .filter(alumno=alumno)
        .select_related(
            "item",
            "item__materia",
            "item__listado",
            "item__listado__programa",
        )
        .order_by(
            "-item__listado__creado_en",   # listados más recientes primero
            "item__fecha_inicio",
            "item__materia__codigo",
        )
    )

    print("[DEBUG] califs count =", califs.count())
  

    return render(
        request,
        "alumnos/detalle.html",
        {
             # Calificaciones
            "califs": califs,
            
            "alumno": alumno,
            "hoy": hoy,   
            # pagos/cargos
            "pagos": pagos,
            "pagos_total": pagos_total,
            "pago_total_mayor_a_cero": pago_total_mayor_a_cero,
            "cargos": cargos,
            "cargos_pendientes": cargos_pendientes,
            "can_view_pagos": can_view_pagos,

            # documentos dinámicos
            "can_view_documentos": can_view_docs,
            "docs": docs,
            "docs_total": docs_total,
            "docs_last_update": docs_last_update,
            "faltantes": faltantes,
            "cargos_todos": cargos_todos,
            "hay_cargos_vinculados": hay_cargos_vinculados,

            # <<< NUEVO en el contexto para pintar en el template >>>
            "fin_programa_is_future": fin_programa_is_future,
            'orden': orden,
            'rows': data,
            'totales': {
            'original': total_original,
            'aplicado': total_aplicado,
            'restante': total_restante,

           
        
            },
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
# Asegúrate de tener:
from datetime import timedelta
from django.utils import timezone


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

            if allowed is None:
                return qs.none()

            base_qs = qs.filter(allowed).distinct()

        # Límite temporal (2 años) salvo flag en perfil
        profile = getattr(user, "profile", None)
        show_all = bool(profile and getattr(profile, "ver_todos_los_pagos", False))
        if not show_all:
            hace_dos_anios = timezone.now().date() - timedelta(days=730)
            base_qs = base_qs.filter(fecha__gte=hace_dos_anios)

        # --- Filtros por fecha (desde/hasta) ---
        fmin = self.request.GET.get("desde")
        fmax = self.request.GET.get("hasta")
        if fmin:
            base_qs = base_qs.filter(fecha__gte=fmin)
        if fmax:
            base_qs = base_qs.filter(fecha__lte=fmax)

        # --- NUEVO: filtros por creado_en (desde/hasta) ---
        cmin = self.request.GET.get("creado_desde")
        cmax = self.request.GET.get("creado_hasta")
        if cmin:
            base_qs = base_qs.filter(creado_en__date__gte=cmin)
        if cmax:
            base_qs = base_qs.filter(creado_en__date__lte=cmax)

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

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        # Mantén los valores de filtros en el contexto para el template
        ctx["desde"] = self.request.GET.get("desde", "")
        ctx["hasta"] = self.request.GET.get("hasta", "")
        ctx["creado_desde"] = self.request.GET.get("creado_desde", "")
        ctx["creado_hasta"] = self.request.GET.get("creado_hasta", "")
        ctx["q"] = self.request.GET.get("q", "")
        return ctx
    
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


from pypdf import PdfWriter, PdfReader
from PIL import Image

from alumnos.models import Alumno, DocumentoAlumno, DocumentoTipo, ProgramaDocumentoRequisito
from alumnos.permisos import user_can_view_documentos  # ajusta si tu helper se llama distinto


from io import BytesIO

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from PIL import Image
import os

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}

def _image_file_to_pdf_bytes(django_file):
    django_file.open("rb")
    try:
        im = Image.open(django_file).convert("RGB")
        W, H = A4
        max_w, max_h = W - 80, H - 160
        iw, ih = im.size
        scale = min(max_w/iw, max_h/ih, 1.0)
        im = im.resize((max(1,int(iw*scale)), max(1,int(ih*scale))), Image.LANCZOS)

        pdf_buf = BytesIO()
        c = canvas.Canvas(pdf_buf, pagesize=A4)
        x = (W - im.size[0]) / 2
        y = (H - im.size[1]) / 2
        from reportlab.lib.utils import ImageReader
        mem = BytesIO(); im.save(mem, format="PNG"); mem.seek(0)
        c.drawImage(ImageReader(mem), x, y, width=im.size[0], height=im.size[1],
                    preserveAspectRatio=True, mask='auto')
        c.showPage(); c.save(); pdf_buf.seek(0)
        return pdf_buf
    finally:
        try: django_file.close()
        except: pass

def draw_fullwidth_image_bottom(c, left_margin, right_margin, bottom_margin, img_path):
    if not img_path or not os.path.isfile(img_path):
        return
    from reportlab.lib.utils import ImageReader
    W, H = c._pagesize  # ← aquí obtenemos el ancho/alto de la página
    img = ImageReader(img_path)
    iw, ih = img.getSize()
    avail_w = W - left_margin - right_margin
    if avail_w <= 0:
        return
    new_h = ih * (avail_w / iw)
    c.drawImage(img, left_margin, bottom_margin, width=avail_w, height=new_h,
                preserveAspectRatio=True, mask='auto')

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

        qs = MovimientoBanco.objects.all()

        signo = self.request.GET.get("signo")
        tipo  = self.request.GET.get("tipo")
        fmin  = self.request.GET.get("desde")
        fmax  = self.request.GET.get("hasta")

        if signo in ("1", "-1"):
            qs = qs.filter(signo=int(signo))
        if tipo:
            qs = qs.filter(tipo__icontains=tipo)

        # ✅ Lógica de rango por defecto (últimos 6 meses) SI NO hay filtros de fecha
        if fmin or fmax:
            if fmin:
                qs = qs.filter(fecha__gte=fmin)
            if fmax:
                qs = qs.filter(fecha__lte=fmax)
        else:
            six_months_ago = timezone.now().date() - timedelta(days=183)
            qs = qs.filter(fecha__gte=six_months_ago)
            # guardamos para prellenar inputs
            self._default_desde = six_months_ago.isoformat()
            self._default_hasta = timezone.now().date().isoformat()

        return qs.order_by("-id")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        qs = self.object_list
        user = self.request.user

        ctx["total_registros"] = qs.count()
        ctx["total_abonos"] = qs.filter(signo=1).aggregate(s=Sum("monto"))["s"] or Decimal("0")
        ctx["total_cargos"] = qs.filter(signo=-1).aggregate(s=Sum("monto"))["s"] or Decimal("0")

        ctx["puede_conciliar"] = (
            user.is_superuser or user.groups.filter(name="Conciliadores Bancarios").exists()
        )
        ctx["puede_deshacer"] = (
            user.is_superuser or user.groups.filter(name="Supervisores Bancarios").exists()
        )

        # Valores por defecto para inputs si no vinieron en GET
        ctx["desde_default"] = getattr(self, "_default_desde", "")
        ctx["hasta_default"] = getattr(self, "_default_hasta", "")
        return ctx
###############################################################
def _salidas_dir():
    base = getattr(settings, "BASE_DIR", Path.cwd())
    # opción alternativa: Path(settings.MEDIA_ROOT) / "salidas"
    return Path(base) / "salidas"

def _print_header(title: str):
    print("\n" + "=" * 80)
    print(f"[{datetime.now().isoformat(timespec='seconds')}] {title}")
    print("=" * 80, flush=True)

###############################################################
SHEET_ID = "1G0P64LVOfxG4siNXmTm0gCORoaPby2W2_wu0Z869Dvk"
SHEET_NAME = "2022"
SHEET_GID = "1206699819"

import io
import os
import sys
import json
import traceback
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from django.shortcuts import redirect
from django.views.decorators.http import require_POST
from django.core.management import call_command


@staff_member_required
@require_POST
def run_movimientos_banco_update(request):
    """
    Ejecuta el comando que lee el Google Sheet (hoja '2022'),
    guarda un JSON y luego hace upsert en DB.
    Imprime en consola cada paso para depurar en Linux.
    """
    _print_header("INICIO importación de movimientos de banco")

    # --- Contexto del proceso / entorno ---
    try:
        uid = os.geteuid() if hasattr(os, "geteuid") else "N/A"
        gid = os.getegid() if hasattr(os, "getegid") else "N/A"
    except Exception:
        uid = gid = "N/A"

    print(f"Python: {sys.version}")
    print(f"Platform: {sys.platform}")
    print(f"PID: {os.getpid()} | UID:GID = {uid}:{gid}")
    print(f"CWD: {os.getcwd()}")
    print(f"__file__: {__file__}")
    print(f"DJANGO_SETTINGS_MODULE: {os.environ.get('DJANGO_SETTINGS_MODULE')}")
    print(f"DEBUG: {getattr(settings, 'DEBUG', None)}")
    print(f"BASE_DIR: {getattr(settings, 'BASE_DIR', None)}")
    print(f"MEDIA_ROOT: {getattr(settings, 'MEDIA_ROOT', None)}")
    print(f"SHEET_ID: {SHEET_ID} | SHEET_NAME: {SHEET_NAME} | SHEET_GID: {SHEET_GID}")

    out_dir = _salidas_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "movimientos_2022.json"
    print(f"out_dir: {out_dir}  (exists={out_dir.exists()}, mode={oct(out_dir.stat().st_mode) if out_dir.exists() else 'N/A'})")
    print(f"out_path: {out_path}")

    # Probar escritura en out_dir (para detectar permisos/bind mounts)
    try:
        probe = out_dir / ".perm_probe"
        probe.write_text("ok", encoding="utf-8")
        print(f"Prueba de escritura OK en {probe} (owner uid={probe.stat().st_uid}, gid={probe.stat().st_gid})")
        probe.unlink(missing_ok=True)
    except Exception as e_probe:
        print(f"[ERROR] No puedo escribir en {out_dir}: {e_probe}")
        traceback.print_exc()
        messages.error(request, f"No puedo escribir en {out_dir}: {e_probe}")
        return redirect("movimientos_banco_lista")

    # Buffers de captura del management command
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()

    # 1) Ejecutar el management command que genera el JSON
    _print_header("EJECUTANDO management command leer_google_sheet")
    try:
        call_command(
            "leer_google_sheet",
            "--por", "nombre",
            "--out-json", str(out_path),
            stdout=stdout_buf,
            stderr=stderr_buf,
        )
    except Exception as e_cmd:
        # Mostrar todo lo capturado
        cmd_out = stdout_buf.getvalue()
        cmd_err = stderr_buf.getvalue()
        print("[EXCEPCIÓN] call_command('leer_google_sheet') lanzó excepción:")
        traceback.print_exc()
        print("--- STDOUT (completo) ---")
        print(cmd_out if cmd_out else "(vacío)")
        print("--- STDERR (completo) ---")
        print(cmd_err if cmd_err else "(vacío)")
        messages.error(request, f"Error al ejecutar importación: {e_cmd}.")
        return redirect("movimientos_banco_lista")

    # Imprimir lo que arrojó el comando (aunque no haya excepción)
    cmd_out = stdout_buf.getvalue()
    cmd_err = stderr_buf.getvalue()
    print("--- STDOUT (completo) ---")
    print(cmd_out if cmd_out else "(vacío)")
    print("--- STDERR (completo) ---")
    print(cmd_err if cmd_err else "(vacío)")

    # 2) Validar el archivo generado
    _print_header("VALIDANDO archivo JSON generado")
    if not out_path.exists():
        print(f"[ERROR] El archivo no existe: {out_path}")
        messages.error(request, f"El comando no generó el archivo: {out_path}")
        return redirect("movimientos_banco_lista")

    try:
        stat = out_path.stat()
        print(f"Archivo generado: {out_path} | size={stat.st_size} bytes | uid={stat.st_uid} gid={stat.st_gid} mode={oct(stat.st_mode)}")
    except Exception as e_stat:
        print(f"[WARN] No pude leer stat del archivo: {e_stat}")

    # 3) Cargar JSON
    _print_header("LEYENDO JSON")
    try:
        raw = out_path.read_text(encoding="utf-8")
        print(f"Primeras 500 chars del JSON:\n{raw[:500]}")
        data = json.loads(raw)
        print(f"JSON OK. Tipo: {type(data)} | resumen: {('len=' + str(len(data))) if hasattr(data, '__len__') else 'sin __len__'}")
    except Exception as e_json:
        print(f"[ERROR] No pude leer/parsear el JSON ({out_path}): {e_json}")
        traceback.print_exc()
        messages.error(request, f"No pude leer el JSON ({out_path}): {e_json}")
        return redirect("movimientos_banco_lista")

    # 4) Guardar/actualizar en DB
    _print_header("UPSERT en Base de Datos")
    try:
       pass
    except Exception:
        # si ya estaba importado arriba, ignora esta sección
        pass

    try:
        res = upsert_movimientos(
            data,
            source_sheet_id=SHEET_ID,
            source_sheet_name=SHEET_NAME,
            source_gid=SHEET_GID,
        )
        created = res.get("created", 0)
        updated = res.get("updated", 0)
        print(f"UPSERT OK → Creados: {created} | Actualizados: {updated}")
        messages.success(request, f"Movimientos actualizados. Creados: {created} · Actualizados: {updated}.")
    except Exception as e_db:
        print(f"[ERROR] Falló upsert_movimientos: {e_db}")
        traceback.print_exc()
        messages.error(request, f"Error guardando en BD: {e_db}")

    _print_header("FIN importación de movimientos de banco")
    sys.stdout.flush()
    sys.stderr.flush()
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

    # Normaliza
    if value is not None:
        value = (value or "").strip()
        if not value:
            value = None

    # Valida longitud
    if value and len(value) > 200:
        return JsonResponse(
            {"ok": False, "error": "El nombre no puede exceder 200 caracteres."},
            status=400,
        )

    mov.nombre_detectado_save = value
    mov.save(update_fields=["nombre_detectado_save", "updated_at"])

    # Busca el alumno si existe
    alumno = getattr(mov, "alumno", None)
    if alumno is None:
        # si tienes campo numero_alumno, intenta buscarlo
        num = getattr(mov, "numero_alumno", None)
        if num:
            try:
                from alumnos.models import Alumno
                alumno = Alumno.objects.select_related("informacionEscolar").get(
                    numero_estudiante=num
                )
            except Alumno.DoesNotExist:
                alumno = None

    return JsonResponse({
        "ok": True,
        "value": mov.nombre_detectado_save,
        "alumno": str(alumno) if alumno else None,
        "informacionEscolar": str(alumno.informacionEscolar) if getattr(alumno, "informacionEscolar", None) else None,
    })


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


###################################################################
# alumnos/views.py
# alumnos/views.py
import io
import re
import pandas as pd
from datetime import datetime, date
from pathlib import Path

from django.http import HttpResponse, Http404
from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.staticfiles import finders
from django.template.loader import render_to_string

# ==============================
# PDF helper (WeasyPrint -> xhtml2pdf fallback)
# ==============================
def html_to_pdf(html: str, request=None) -> bytes:
    """
    Genera PDF desde HTML. Usa WeasyPrint (si está disponible) con base_url
    para que las rutas /static/ funcionen. Márgenes en 0 porque la plantilla
    ya está maquetada a página completa A4.
    """
    try:
        from weasyprint import HTML, CSS
        base_url = request.build_absolute_uri("/") if request is not None else None
        return HTML(string=html, base_url=base_url).write_pdf(
            stylesheets=[CSS(string="""
                @page { size: A4; margin: 0; }
                html, body { margin: 0; padding: 0; }
            """)]
        )
    except Exception:
        # Fallback: xhtml2pdf
        
        buf = io.BytesIO()
        r = pisa.CreatePDF(io.StringIO(html), dest=buf)
        if r.err:
            raise RuntimeError("No se pudo generar el PDF.")
        return buf.getvalue()

# ==============================
# Utilidades de parseo
# ==============================
def _parse_money(val):
    if val is None:
        return None
    s = str(val).strip()
    if not s:
        return None
    s = s.replace("$", "").replace(",", "").replace(" ", "")
    # caso latino 1.234,56
    if "." in s and "," in s and s.rfind(",") > s.rfind("."):
        s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except Exception:
        try:
            import re as _re
            return float(_re.sub(r"[^\d.\-]", "", s))
        except Exception:
            return None

def _parse_date(val):
    if not val:
        return None
    if isinstance(val, (datetime, date)):
        return val if isinstance(val, date) else val.date()
    if hasattr(val, "to_pydatetime"):
        return val.to_pydatetime().date()
    s = str(val).strip()
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%y", "%d-%m-%y"):
        try:
            return datetime.strptime(s, fmt).date()
        except Exception:
            pass
    return None

def _norm(x):
    """Normaliza texto para comparar etiquetas."""
    if x is None:
        return ""
    import re as _re
    s = str(x).strip()
    return _re.sub(r"\s+", " ", s).lower()

def _get(df, r, c):
    try:
        v = df.iloc[r, c]
    except Exception:
        return None
    return None if pd.isna(v) else str(v).strip()

def find_label(df, pattern):
    """
    Busca una celda cuyo texto normalizado haga match con el regex 'pattern' (lower).
    Devuelve (r, c) o None.
    """
    import re as _re
    rx = _re.compile(pattern)
    rows, cols = df.shape
    for r in range(rows):
        for c in range(cols):
            txt = _norm(df.iloc[r, c])
            if txt and rx.search(txt):
                return r, c
    return None

def value_right(df, r, c, steps=1):
    """Valor a la derecha de la etiqueta (steps columnas)."""
    return _get(df, r, c + steps)

# ==============================
# Vista: Recibo desde Excel no tabular
# ==============================
@staff_member_required
def recibo2_from_excel(request):
    """
    Lee un Excel de recibo (no tabular) ubicado en /static (por defecto iuaf/pago.xlsx),
    detecta etiquetas y toma los valores adyacentes. NO guarda nada. Devuelve un PDF.

    Query opcional:
      - ?archivo=iuaf/OTRO.xlsx  (ruta relativa dentro de /static)
    """
    # -------- localizar archivo --------
    rel_path = (request.GET.get("archivo") or "iuaf/pago.xlsx").lstrip("/")
    static_path = finders.find(rel_path)
    if not static_path:
        static_path = Path(settings.BASE_DIR) / "static" / rel_path
        if not static_path.exists():
            raise Http404(f"No encuentro el Excel en static: {rel_path}")

    # -------- leer hoja completa como texto --------
    try:
        df = pd.read_excel(static_path, header=None, dtype=str)
    except Exception as e:
        raise Http404(f"Excel inválido ({rel_path}): {e}")

    if df.empty:
        raise Http404("El Excel no contiene datos.")

    # -------- extraer campos por etiquetas --------
    pos = find_label(df, r"\bfolio\b")
    folio = value_right(df, *pos, steps=1) if pos else ""

    pos = find_label(df, r"\brecibimos\s*de\b")
    nombre = value_right(df, *pos, steps=1) if pos else ""

    pos = find_label(df, r"\bcurp\b")
    curp = value_right(df, *pos, steps=1) if pos else ""

    pos = find_label(df, r"\bconcepto\s*de\s*pago\b")
    concepto = value_right(df, *pos, steps=1) if pos else ""

    pos = find_label(df, r"#\s*pago\b")
    detalle = value_right(df, *pos, steps=1) if pos else ""

    pos = find_label(df, r"\bforma\s*de\s*pago\b")
    forma = value_right(df, *pos, steps=1) if pos else ""

    pos = find_label(df, r"\bno\.?\s*de\s*autorizaci[oó]n\b")
    no_auto = value_right(df, *pos, steps=1) if pos else ""

    pos = find_label(df, r"\bfecha\s*de\s*pago\b")
    fecha_raw = value_right(df, *pos, steps=1) if pos else ""
    fecha_dt = _parse_date(fecha_raw)

    # Programa (título grande)
    pos = find_label(df, r"(doctorado|maestr[ií]a|licenciatura)")
    programa = _get(df, *pos) if pos else ""

    # Monto (a la derecha de "La Cantidad de:")
    pos = find_label(df, r"\bla\s*cantidad\s*de\b")
    monto = ""
    if pos:
        for step in (1, 2, 3, 4):
            cand = value_right(df, *pos, steps=step)
            if cand and any(ch.isdigit() for ch in cand):
                monto = cand
                break
    monto_f = _parse_money(monto)

    # -------- contexto para plantilla --------
    ctx = {
        "institucion": {
            "nombre": "INSTITUTO UNIVERSITARIO DE ALTA FORMACIÓN IUAF SC.",
            "rfc": "IUA170913LI2",
            "cct": "23PSU0064H",
            "ciudad": "Cancún, Q.R.",
        },
        "folio": folio or "—",
        "nombre": nombre or "—",
        "curp": curp or "—",
        "programa": programa or "—",
        "concepto": concepto or "—",
        "detalle": detalle or "—",
        "forma_pago": forma or "—",
        "sede": "",  # añade etiqueta en Excel si la quieres extraer
        "no_autorizacion": no_auto or "—",
        "fecha_pago": fecha_dt.strftime("%d/%m/%Y") if fecha_dt else (fecha_raw or "—"),
        "monto": f"${monto_f:,.2f}" if monto_f is not None else (monto or "—"),
        "hoy": datetime.now().strftime("%d de %B de %Y"),
        "extemporaneo": bool(find_label(df, r"\bpago\s*extempor[aá]neo\b")),
    }

    # -------- render + PDF --------
    html = render_to_string("reportes/recibo2.html", ctx)
    pdf_bytes = html_to_pdf(html, request)   # <-- importante pasar request
    filename = f"recibo_{ctx['folio'] or 'sin_folio'}.pdf"

    resp = HttpResponse(pdf_bytes, content_type="application/pdf")
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp

################################################

from django.shortcuts import render, get_object_or_404
from django.utils import timezone
from .models import PagoDiario

# ===== Helpers =====
MESES_ES = ["", "enero", "febrero", "marzo", "abril", "mayo", "junio",
            "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]

def fecha_larga_es(d):
    """2025-10-27 -> '27 de octubre de 2025'"""
    if not d:
        d = timezone.localdate()
    return f"{d.day} de {MESES_ES[d.month]} de {d.year}"

def formatea_moneda(amount):
    """Devuelve '3,497.00' y '$ 3,497.00 MXN'."""
    if amount is None:
        return "0.00", "$ 0.00 MXN"
    s = f"{amount:,.2f}"
    return s, f"$ {s} MXN"

def cantidad_en_letra_mx(amount):
    """
    '3497.00' -> 'TRES MIL CUATROCIENTOS NOVENTA Y SIETE 00/100 PESOS'
    Requiere num2words para texto; si no está, hace fallback simple.
    """
    try:
        from num2words import num2words
        entero = int(amount or 0)
        centavos = int(round(((amount or 0) - entero) * 100))
        palabras = num2words(entero, lang="es").upper()
        return f"{palabras} {centavos:02d}/100 PESOS"
    except Exception:
        entero = int(amount or 0)
        centavos = int(round(((amount or 0) - entero) * 100))
        return f"{entero:,} {centavos:02d}/100 PESOS".replace(",", ".").upper()

def nombre_completo_alumno(alumno):
    from django.utils.text import capfirst
    if not alumno:
        return ""
    partes = [alumno.nombre or "", alumno.apellido_p or "", alumno.apellido_m or ""]
    return capfirst(" ".join(p for p in partes if p).strip())

# ===== Vista =====
def recibo_pago_carta(request, pk):
    """
    Renderiza el recibo 'Carta' llenando datos desde PagoDiario (+ Alumno / MovimientoBanco).
    """
    pago = get_object_or_404(
        PagoDiario.objects.select_related("alumno", "movimiento"),
        pk=pk
    )
    alumno = pago.alumno
    mov = getattr(pago, "movimiento", None)

    # Folio
    folio = pago.folio or str(pago.pk)

    # Lugar / Fecha emisión
    lugar_emision = (pago.sede or "Cancún, Q.R.").strip()
    fecha_emision = fecha_larga_es(pago.fecha or timezone.localdate())

    # Monto
    monto_str, monto_con_signo = formatea_moneda(pago.monto or 0)
    monto_letra = cantidad_en_letra_mx(pago.monto or 0)

    # Alumno / CURP
    nombre_recibe = nombre_completo_alumno(alumno) or (pago.nombre or "").strip()
    curp = (pago.curp or getattr(alumno, "curp", "") or "").upper()

    # Programa
    if pago.programa:
        programa = pago.programa
    else:
        try:
            programa = alumno.programa_clave  # property en tu modelo
        except Exception:
            programa = ""

    # Concepto
    concepto = (pago.concepto or pago.pago_detalle or "").upper()

    # Forma / Fecha pago
    forma_pago = (pago.forma_pago or (getattr(mov, "tipo", "") or "")).upper()
    fecha_pago = pago.fecha or getattr(mov, "fecha", None) or timezone.localdate()
    fecha_pago_str = fecha_pago.strftime("%d/%m/%Y")

    # Beca
    beca_pct = 0  # cámbialo si lo traes del plan financiero

    # Estado (oportuno/extemporáneo)
    oportuno = bool(pago.pago_oportuno)

    contexto = {
        "institucion": {
            "nombre": "INSTITUTO UNIVERSITARIO DE ALTA FORMACIÓN IUAF SC.",
            "rfc": "IUA170913LI2",
            "cct": "23PSU0064H",
            "ciudad": "Cancún, Q.R.",
            "telefono": "9982536750",
            "email": "cadministrativa@iuaf.edu.mx",
            "direccion": "Blvd. Kukulkán MZ.30 LT.D-9-B KM 3.5 Zona Hotelera",
        },
        "hoy": timezone.localdate(),

        "pago": {
            "pk": pago.pk,
            "folio": folio,
            "cantidad": monto_str,
            "cantidad_letra": monto_letra,
            "forma_pago": forma_pago,
            "fecha_pago": fecha_pago_str,
            "beca": beca_pct,
            "concepto": concepto,
            "programa": (programa or "").upper(),
            "oportuno": oportuno,
            "monto_con_signo": monto_con_signo,
            "nombre": nombre_recibe,  # 👈 agregado para que la plantilla pueda usar {{ pago.nombre }}
        },

        "alumno": {
            "nombre_completo": nombre_recibe,
            "curp": curp,
            "numero": getattr(alumno, "numero_estudiante", "") if alumno else "",
        },

        "lugar_emision": lugar_emision,
        "fecha_emision": fecha_emision,
    }
    return render(request, "reportes/recibo_carta.html", contexto)
##########################################################################################
def estado_cuenta(request, numero_estudiante):
    alumno = get_object_or_404(
        Alumno.objects.select_related(
            "informacionEscolar",
            "pais", "estado",
        ),
        pk=numero_estudiante
    )

    info = getattr(alumno, "informacionEscolar", None)

    # ================= Pagos reales del alumno =================
    pagos_qs = (
        PagoDiario.objects
        .filter(alumno=alumno)
        .order_by("fecha", "pk")
    )

    numero_colegiatura = pagos_qs.first().alumno.informacionEscolar.meses_programa if pagos_qs.exists() else 0
    precio_final  = pagos_qs.first().alumno.informacionEscolar.precio_final if pagos_qs.exists() else 0
    precio_total = precio_final * numero_colegiatura

    pagos = []
    for p in pagos_qs:
        pagos.append({
            "monto": float(p.monto or 0),
            "grado": getattr(getattr(info, "programa", None), "codigo", "") or getattr(info, "grupo", "") or "",
            "forma_pago": p.forma_pago or "",
            "fecha_pago": p.fecha.strftime("%d/%m/%Y") if p.fecha else "",
            "concepto": p.concepto or "",
            "detalle": p.pago_detalle or "",
            "programa": p.programa or (getattr(getattr(info, "programa", None), "nombre", "") or ""),
        })

    # ================= Cálculos de totales =================
    total_pagado_num = pagos_qs.aggregate(s=Sum("monto"))["s"] or Decimal("0.00")
    total_pagado_num = Decimal(total_pagado_num)

    colegiatura = Decimal(str(getattr(info, "precio_colegiatura", 0) or 0))
    n_colegiaturas = (
        getattr(info, "numero_reinscripciones", None)
        or getattr(info, "meses_programa", None)
        or 20
    )

    total_programa_num = colegiatura * Decimal(n_colegiaturas or 0)
    if total_programa_num <= 0:
        total_programa_num = total_pagado_num

    adeudo_num = total_programa_num - total_pagado_num
    if adeudo_num < 0:
        adeudo_num = Decimal("0.00")

    # ================= Datos de institución =================
    institucion = {
        "nombre": "INSTITUTO UNIVERSITARIO DE ALTA FORMACIÓN IUAF SC.",
        "direccion": "Blvd Kukulcan km 3.5 plaza nautilus local 53, Zona Hotelera",
        "ciudad": "Cancún, Q.ROO.",
        "telefono": "998 253 6750",
        "rfc": "IUA170913LI2",
        "cct": "23PSU0064H",
        "email": "cadministrativa@iuaf.edu.mx",
    }

    # ================= Datos del alumno =================
    alumno_ctx = {        
        "matricula": getattr(info, "matricula", "") or "",
        "nombre": f"{alumno.nombre} {alumno.apellido_p or ''} {alumno.apellido_m or ''}".strip(),
        "grupo": getattr(info, "grupo", "") or "",
        "programa": getattr(getattr(info, "programa", None), "nombre", "") or "",
        "curp": alumno.curp or "",
        "no_alumno": alumno.numero_estudiante,
        "fecha_1er_pago": getattr(info, "inicio_programa", None).strftime("%d/%m/%Y")
            if getattr(info, "inicio_programa", None)
            else "",
    }

    deuda = precio_total - total_pagado_num

    # ================= Contexto final =================
    context = {
        "institucion": institucion,
        "alumno": alumno_ctx,
        "pagos": pagos,
        "total_programa": f"{total_programa_num:,.2f}",
        "total_pagado": f"{total_pagado_num:,.2f}",
        "adeudo": f"{adeudo_num:,.2f}",
        "numero_colegiatura": numero_colegiatura,
        "precio_final": f"{precio_final:,.2f}",
        "precio_total": f"{precio_total:,.2f}",
        "deuda": f"{deuda:,.2f}",
        # imágenes (coloca en /static/iuaf/)
        "logo": "iuaf/logo-placeholder.png",
        "qr": "iuaf/qr-placeholder.png",
        "stamp": "iuaf/stamp-placeholder.png",
    }

    return render(request, "reportes/estado_cuenta.html", context)
###########################################################################################
from calendar import monthrange
def _mes_year_siguiente(base: date, offset: int) -> date:
    y = base.year + (base.month - 1 + offset) // 12
    m = (base.month - 1 + offset) % 12 + 1
    day = 1
    last_day = monthrange(y, m)[1]
    return date(y, m, min(day, last_day))

def _resolve_concepto(request):
    concepto_id = request.POST.get("concepto_id")
    if concepto_id and concepto_id.isdigit():
        c = ConceptoPago.objects.filter(pk=int(concepto_id)).first()
        if c:
            return c
    c = ConceptoPago.objects.filter(codigo="COLEGIATURA").first()
    if c:
        return c
    return ConceptoPago.objects.first()

######
def _resolve_concepto_inscripcion():
    """
    Busca un ConceptoPago para inscripción por códigos comunes o por nombre.
    Ajusta los códigos a tu catálogo si usas otros.
    """
    # Prioridad por código exacto
    for code in ("INSCRIPCION", "INSCRIPCIÓN", "INS"):
        try:
            return ConceptoPago.objects.get(codigo=code)
        except ConceptoPago.DoesNotExist:
            pass
    # Fallback por nombre
    try:
        return ConceptoPago.objects.get(nombre__icontains="inscrip")
    except ConceptoPago.DoesNotExist:
        return None





from datetime import date, timedelta
from decimal import Decimal
from django.db import transaction
from django.http import JsonResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST

# Si no lo tienes en utilidades:
from calendar import monthrange
def add_months_clamp(d: date, months: int) -> date:
    """Suma 'months' meses a d. Si el mes destino no tiene ese día, ajusta al último del mes."""
    y = d.year + (d.month - 1 + months) // 12
    m = (d.month - 1 + months) % 12 + 1
    last_day = monthrange(y, m)[1]
    day = min(d.day, last_day)
    return date(y, m, day)

def _to_decimal(v, default="0.00"):
    try:
        return Decimal(v or default)
    except Exception:
        return Decimal(default)

# Fallback por si no tienes este helper:
def _resolve_concepto_reinscripcion():
    for code in ("REINSCRIPCION", "REINSCRIPCIÓN", "REINS"):
        try:
            return ConceptoPago.objects.get(codigo=code)
        except ConceptoPago.DoesNotExist:
            pass
    try:
        return ConceptoPago.objects.get(nombre__icontains="reinscrip")
    except ConceptoPago.DoesNotExist:
        return None


@login_required
@require_POST
def generar_cargos_mensuales(request, numero_estudiante):
    alumno = get_object_or_404(Alumno, pk=numero_estudiante)

    # permisos
    try:
        from alumnos.permisos import user_can_edit_alumno
        if not user_can_edit_alumno(request.user, alumno):
            return HttpResponseForbidden("No tienes permiso para generar cargos para este alumno.")
    except Exception:
        if not (request.user.is_staff or request.user.is_superuser):
            return HttpResponseForbidden("No tienes permiso para generar cargos para este alumno.")

    info = getattr(alumno, "informacionEscolar", None)
    if not info:
        return JsonResponse({"ok": False, "error": "El alumno no tiene Información Escolar."}, status=400)

    meses = int(info.meses_programa or 0)
    if meses <= 0:
        return JsonResponse({"ok": False, "error": "Meses de programa inválido (<= 0)."}, status=400)

    base = info.inicio_programa or date.today()

    # Concepto de mensualidad/colegiatura
    concepto_mensual = _resolve_concepto(request)
    if not concepto_mensual:
        return JsonResponse({"ok": False, "error": "No se encontró un Concepto de pago para crear cargos (mensual)."}, status=400)

    # Concepto de inscripción (opcional)
    concepto_insc = _resolve_concepto_inscripcion()

    # Concepto de reinscripción (para hitos)
    concepto_reins = _resolve_concepto_reinscripcion()

    # ---- Monto mensual (colegiatura / precio_final) ----
    monto_mensual = _to_decimal(info.precio_final if info.precio_final not in (None, "") else info.precio_colegiatura)

    # ---- Monto inscripción (si hay) ----
    insc_monto = _to_decimal(info.precio_inscripcion)

    # Resumen para respuesta
    creados, existentes, actualizados_venc = 0, 0, 0
    created_ids = []
    insc_created = False
    insc_existing = False
    insc_id = None

    # Reinscripciones (hitos)
    reins_resumen = []
    reins_omitidos_fuera_rango = 0

    with transaction.atomic():
        # --- A) INSCRIPCIÓN (una sola vez, en la fecha base) ---
        if concepto_insc and insc_monto > 0:
            insc_fecha = base
            insc_vence = insc_fecha + timedelta(days=6)
            insc_obj, insc_was_created = Cargo.objects.get_or_create(
                alumno=alumno,
                concepto=concepto_insc,
                fecha_cargo=insc_fecha,
                defaults={
                    "monto": insc_monto,
                    "pagado": False,
                    "fecha_vencimiento": insc_vence,
                },
            )
            insc_id = insc_obj.id
            if insc_was_created:
                insc_created = True
            else:
                insc_existing = True
                if insc_obj.fecha_vencimiento is None:
                    insc_obj.fecha_vencimiento = insc_vence
                    insc_obj.save(update_fields=["fecha_vencimiento"])

        # --- B) CARGOS MENSUALES (colegiatura) ---
        for i in range(meses):
            fch = _mes_year_siguiente(base, i)     # tu helper (ej. fija al día 6)
            vence = fch + timedelta(days=6)

            obj, created = Cargo.objects.get_or_create(
                alumno=alumno,
                concepto=concepto_mensual,
                fecha_cargo=fch,
                defaults={
                    "monto": monto_mensual,
                    "pagado": False,
                    "fecha_vencimiento": vence,
                },
            )
            if created:
                creados += 1
                created_ids.append(obj.id)
            else:
                existentes += 1
                if obj.fecha_vencimiento is None:
                    obj.fecha_vencimiento = vence
                    obj.save(update_fields=["fecha_vencimiento"])
                    actualizados_venc += 1

        # --- C) REINSCRIPCIONES (varios hitos del programa) ---
        #   - Usa el monto del hito si lo trae; si no, usa Programa.reinscripcion (default).
        if concepto_reins and info.programa:
            hitos = info.programa.reinscripciones_hitos.filter(activo=True).order_by("meses_offset")
            for h in hitos:
                mes_obj = int(h.meses_offset or 0)
                if mes_obj <= 0:
                    continue

                # (opcional) Omitir hitos que exceden la duración del plan:
                if info.meses_programa and mes_obj > int(info.meses_programa):
                    reins_omitidos_fuera_rango += 1
                    reins_resumen.append({
                        "mes_objetivo": mes_obj,
                        "estado": "omitido_fuera_de_rango",
                        "id": None,
                    })
                    continue

                fch_reins = add_months_clamp(base, mes_obj)
                # Si tus mensuales fijan día 6 y quieres unificar:
                # fch_reins = fch_reins.replace(day=6)

                vence_reins = fch_reins + timedelta(days=6)
                monto_reins = _to_decimal(h.monto if h.monto not in (None, "") else getattr(info.programa, "reinscripcion", None))

                obj_reins, created_reins = Cargo.objects.get_or_create(
                    alumno=alumno,
                    concepto=concepto_reins,
                    fecha_cargo=fch_reins,
                    defaults={
                        "monto": monto_reins,
                        "pagado": False,
                        "fecha_vencimiento": vence_reins,
                    },
                )
                if not created_reins and obj_reins.fecha_vencimiento is None:
                    obj_reins.fecha_vencimiento = vence_reins
                    obj_reins.save(update_fields=["fecha_vencimiento"])

                reins_resumen.append({
                    "mes_objetivo": mes_obj,
                    "monto": f"{monto_reins:.2f}",
                    "fecha": fch_reins.strftime("%Y-%m-%d"),
                    "vence": vence_reins.strftime("%Y-%m-%d"),
                    "creado": bool(created_reins),
                    "existente": (not created_reins),
                    "id": obj_reins.id,
                    "estado": "creado" if created_reins else "existente",
                })

    # Respuesta
    return JsonResponse({
        "ok": True,
        # Mensuales
        "creados": creados,
        "existentes": existentes,
        "actualizados_venc": actualizados_venc,
        "concepto_mensual": getattr(concepto_mensual, "codigo", str(concepto_mensual)),
        "monto_mensual": f"{monto_mensual:.2f}",
        "desde": base.strftime("%Y-%m-%d"),
        "meses": meses,
        "ids": created_ids,

        # Inscripción
        "inscripcion": {
            "intentado": bool(concepto_insc and insc_monto > 0),
            "concepto": getattr(concepto_insc, "codigo", None),
            "monto": f"{insc_monto:.2f}",
            "creado": insc_created,
            "existente": insc_existing,
            "id": insc_id,
        },

        # Reinscripciones (hitos)
        "reinscripciones": reins_resumen,
        "reins_omitidos_fuera_rango": reins_omitidos_fuera_rango,
        "concepto_reinscripcion": getattr(concepto_reins, "codigo", None),
    })


############################################################################################
# views.py
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone
from django.db.models import Q, Case, When, Value, BooleanField
from django.db.models.functions import Coalesce
from django.core.paginator import Paginator

from alumnos.models import Cargo  # ajusta el import a tu app

@login_required
def cargos_pendientes_todos(request):
    """
    Lista cargos de TODOS los alumnos que:
      - no están pagados (pagado=False), y
      - ya están en fecha de pago (fecha_cargo <= hoy) o ya vencieron (fecha_vencimiento <= hoy).
    Muestra vencidos primero y resalta en rojo.
    """
    hoy = timezone.now().date()

    # Filtros opcionales (búsqueda sencilla)
    q = (request.GET.get("q") or "").strip()

    cargos = (
        Cargo.objects
        .filter(pagado=False)
        .filter(
            Q(fecha_cargo__lte=hoy) |
            Q(fecha_vencimiento__lte=hoy)
        )
        .annotate(
            due_date=Coalesce("fecha_vencimiento", "fecha_cargo"),
            is_overdue=Case(
                When(Q(fecha_vencimiento__isnull=False) & Q(fecha_vencimiento__lt=hoy), then=Value(True)),
                When(Q(fecha_vencimiento__isnull=True)  & Q(fecha_cargo__lt=hoy),         then=Value(True)),
                default=Value(False),
                output_field=BooleanField(),
            )
        )
        .select_related("alumno", "concepto")
        .order_by(
            # Vencidos primero
            Case(When(is_overdue=True, then=Value(0)), default=Value(1)),
            "-due_date",
            "-id",
        )
    )

    if q:
        # Búsqueda por número, nombre y correo (ajusta campos si deseas)
        cargos = cargos.filter(
            Q(alumno__numero_estudiante__icontains=q) |
            Q(alumno__nombre__icontains=q) |
            Q(alumno__apellido_p__icontains=q) |
            Q(alumno__apellido_m__icontains=q) |
            Q(alumno__email__icontains=q)
        )

    paginator = Paginator(cargos, 50)  # 50 por página
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(
        request,
        "alumnos/cargos_pendientes_todos.html",
        {
            "page_obj": page_obj,
            "q": q,
            "hoy": hoy,
        },
    )
############################################################################################
from .models import Cargo
from .forms import CargoForm

@login_required
def cargo_crear(request, pk):
    alumno = get_object_or_404(
        Alumno.objects.select_related(
            "pais", "estado", "informacionEscolar",
            "informacionEscolar__programa", "informacionEscolar__sede",
        ),
        pk=pk,
    )

    # ---- Permisos (similar a alumnos_detalle) ----
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
        return HttpResponseForbidden("No tienes permiso para crear cargos para este alumno.")

    if request.method == "POST":
        form = CargoForm(request.POST)
        if form.is_valid():
            cargo = form.save(commit=False)
            cargo.alumno = alumno          # <- fija alumno
            cargo.pagado = False           # <- por defecto
            cargo.save()
            messages.success(request, "Cargo creado correctamente.")

            # Redirección a donde venías (si trae ?next=...), o al detalle con la pestaña "todos".
            next_url = request.GET.get("next")
            if not next_url:
                next_url = reverse("alumnos_detalle", args=[alumno.pk]) + "#pane-todos"
            return redirect(next_url)
    else:
        form = CargoForm()

    return render(request, "alumnos/cargo_form.html", {
        "alumno": alumno,
        "form": form,
        "titulo": "Añadir cargo",
    })

############################################################################################
@login_required
def cargo_editar(request, alumno_pk, cargo_id):
    alumno = get_object_or_404(
        Alumno.objects.select_related(
            "pais", "estado", "informacionEscolar",
            "informacionEscolar__programa", "informacionEscolar__sede",
        ),
        pk=alumno_pk,
    )
    cargo = get_object_or_404(Cargo.objects.select_related("alumno", "concepto"), pk=cargo_id)

    # Verifica que el cargo sea del mismo alumno
    if cargo.alumno_id != alumno.pk:
        return HttpResponseForbidden("Este cargo no pertenece a este alumno.")

    # ---- Permisos (mismo criterio que detalle) ----
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
        return HttpResponseForbidden("No tienes permiso para editar cargos de este alumno.")

    # (Opcional) si no quieres permitir editar cargos pagados:
    # if cargo.pagado:
    #     return HttpResponseForbidden("No es posible editar un cargo pagado.")

    if request.method == "POST":
        form = CargoForm(request.POST, instance=cargo)
        if form.is_valid():
            cargo_edit = form.save(commit=False)
            # Blindaje: no permitir cambiar alumno ni pagado vía formulario
            cargo_edit.alumno_id = cargo.alumno_id
            cargo_edit.pagado = cargo.pagado
            cargo_edit.save()
            messages.success(request, "Cargo actualizado correctamente.")
            next_url = request.GET.get("next")
            if not next_url:
                next_url = reverse("alumnos_detalle", args=[alumno.pk]) + "#pane-todos"
            return redirect(next_url)
    else:
        form = CargoForm(instance=cargo)

    return render(request, "alumnos/cargo_form.html", {
        "alumno": alumno,
        "form": form,
        "titulo": "Editar cargo",
    })

###########################################################################
@require_POST
def cargo_eliminar(request, alumno_id, cargo_id):
    if not request.user.is_authenticated:
        return HttpResponseForbidden('No autorizado')
    cargo = get_object_or_404(Cargo, pk=cargo_id, alumno_id=alumno_id)
    # opcional: bloquear si pagado
    if getattr(cargo, 'pagado', False):
        return JsonResponse({'ok': False, 'error': 'No se puede eliminar un cargo pagado.'}, status=400)
    cargo.delete()
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'ok': True})
    next_url = request.GET.get('next') or request.META.get('HTTP_REFERER') or '/'
    return redirect(next_url)
############################################################################
from .servicios import calcular_saldos_por_concepto
@login_required
def saldos_por_concepto_view(request, alumno_id, concepto_codigo):
    alumno = get_object_or_404(Alumno, pk=alumno_id)
    data = calcular_saldos_por_concepto(alumno, concepto_codigo=concepto_codigo, restar_mas_recientes=True)
    return render(request, 'alumnos/saldos_por_concepto.html', {'alumno': alumno, 'data': data})

#####################################################################
from .cartera import calcular_cargos_con_saldo

def cargos_con_saldo_view(request, alumno_id):
    alumno = get_object_or_404(Alumno, pk=alumno_id)
    # Si quieres permitir cambiar la regla de prioridad (?orden=antiguos)
    orden = request.GET.get('orden', 'recientes')
    restar_mas_recientes = (orden != 'antiguos')

    data = calcular_cargos_con_saldo(alumno, restar_pagos_mas_recientes=restar_mas_recientes)

    # Totales
    total_original = sum(d['monto_original'] for d in data) if data else 0
    total_aplicado = sum(d['monto_aplicado'] for d in data) if data else 0
    total_restante = sum(d['monto_restante'] for d in data) if data else 0

    ctx = {
        'alumno': alumno,
        'rows': data,
        'totales': {
            'original': total_original,
            'aplicado': total_aplicado,
            'restante': total_restante,
        },
        'orden': orden,
    }
    return render(request, 'alumnos/cargos_con_saldo.html', ctx)

#############################################################################################################################################
import os
import mimetypes
import traceback
import logging
from email.mime.image import MIMEImage
from io import BytesIO

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.staticfiles import finders
from django.shortcuts import get_object_or_404, redirect
from django.template.loader import render_to_string
from django.utils import timezone
from django.core.mail import EmailMultiAlternatives

from .models import Alumno  # ajusta si está en otra app

logger = logging.getLogger(__name__)

def _dbg(msg):
    # Imprime a la consola y también al logger
    print(f"[enviar_bienvenida_estatica] {msg}")
    logger.info(msg)

# =========================
# Helper: recoger archivos estáticos de una carpeta
# =========================
def collect_program_docs(rel_dir: str):
    items, candidates = [], []

    for finder in finders.get_finders():
        if hasattr(finder, "locations"):
            for prefix, root in getattr(finder, "locations", []):
                sub = os.path.join(prefix, rel_dir) if prefix else rel_dir
                candidates.append(os.path.join(root, sub))
        if hasattr(finder, "storages"):
            for storage in finder.storages.values():
                root = getattr(storage, "location", None)
                if root:
                    candidates.append(os.path.join(root, rel_dir))

    for cand in candidates:
        if os.path.isdir(cand):
            for name in os.listdir(cand):
                path = os.path.join(cand, name)
                if os.path.isfile(path):
                    mime, _ = mimetypes.guess_type(path)
                    items.append((path, name, mime or "application/octet-stream"))

    seen, unique = set(), []
    for abs_path, fname, mime in items:
        if abs_path not in seen:
            unique.append((abs_path, fname, mime))
            seen.add(abs_path)
    _dbg(f"collect_program_docs('{rel_dir}') → {len(unique)} archivo(s).")
    return unique

# =========================
# Helper: construir contexto para la carta
# =========================
def build_carta_ctx(alumno):
    plan = getattr(alumno, "informacionEscolar", None)
    if not plan or not getattr(plan, "programa_id", None):
        _dbg("build_carta_ctx: sin plan o programa_id.")
        return None, None

    programa = plan.programa
    ctx = {
        "alumno": alumno,
        "plan": plan,
        "programa": programa,
        "institucion": {
            "nombre": "Instituto Universitario de Alta Formación",
            "rfc": "—",
            "cct": "23PSU0064H",
            "direccion": "Blvd. Kukulkán Km 3.5, Plaza Nautilus Int. 53, Cancún, Q.R.",
            "ciudad": "México",
            "telefono": "998 939 4481",
            "email": "cadministrativa@iuaf.edu.mx",
        },
        "hoy": timezone.localdate(),
        "grupo_codigo": getattr(plan, "grupo", "") or "",
        "fecha_inicio": getattr(plan, "inicio_programa", None),
        "fecha_fin": getattr(plan, "fin_programa", None),
        "meses_programa": getattr(plan, "meses_programa", None),
        "inscripcion": getattr(plan, "precio_inscripcion", None),
        "reinscripcion": getattr(plan, "precio_reinscripcion", None),
        "colegiatura_mensual": getattr(plan, "precio_final", None) or getattr(plan, "precio_colegiatura", None),
        "meses_pago": getattr(plan, "meses_programa", None),
        "titulacion": getattr(programa, "titulacion", None) if programa else None,
        "etiqueta_beca": (getattr(plan, "financiamiento", None).beca if getattr(plan, "financiamiento_id", None) else None),
        "asistencia": "Viernes y Sábado",
        "horario": "V: 17 a 21 hrs · S: 9 a 14 hrs",
        "duracion_texto": f"{getattr(plan, 'meses_programa', '—')} MESES",
    }
    _dbg("build_carta_ctx: contexto construido OK.")
    return ctx, plan

# =========================
# PDF helpers
# =========================
def xhtml2pdf_link_callback(uri, rel):
    s_url, s_root = settings.STATIC_URL, getattr(settings, "STATIC_ROOT", "")
    m_url, m_root = settings.MEDIA_URL, getattr(settings, "MEDIA_ROOT", "")

    if uri.startswith(s_url):
        relpath = uri[len(s_url):]
        path = finders.find(relpath)
        if not path and s_root:
            path = os.path.join(s_root, relpath)
        return path or uri

    if m_root and uri.startswith(m_url):
        return os.path.join(m_root, uri[len(m_url):])

    return uri

def html_to_pdf_bytes(html: str, base_url: str) -> bytes:
    try:
        from weasyprint import HTML
        _dbg("html_to_pdf_bytes: intentando WeasyPrint…")
        pdf = HTML(string=html, base_url=base_url).write_pdf()
        _dbg(f"html_to_pdf_bytes: WeasyPrint OK → {len(pdf)} bytes.")
        return pdf
    except Exception as e:
        _dbg(f"WeasyPrint falló: {e}\n{traceback.format_exc()}")

    _dbg("html_to_pdf_bytes: intentando xhtml2pdf…")
    
    pdf_out = BytesIO()
    status = pisa.CreatePDF(
        src=html, dest=pdf_out,
        link_callback=xhtml2pdf_link_callback,
        encoding="utf-8",
    )
    if status.err:
        _dbg("xhtml2pdf: error al generar PDF.")
        raise RuntimeError("xhtml2pdf no pudo generar el PDF (revisa CSS/recursos).")
    data = pdf_out.getvalue()
    _dbg(f"html_to_pdf_bytes: xhtml2pdf OK → {len(data)} bytes.")
    return data

###################################################


def generar_carta_inscripcion_pdf(alumno, request) -> str | None:
    """
    Genera el PDF de la carta de inscripción en:
        <STATIC_WRITE_ROOT>/iuaf/bienvenida/pdf/<numero_estudiante>.pdf
    Devuelve la ruta absoluta creada si OK, o None si hubo error.
    NO redirige ni responde; solo hace el trabajo.
    """
    plan = getattr(alumno, "informacionEscolar", None)
    if not plan or not getattr(plan, "programa_id", None):
        _dbg("generar_carta_inscripcion_pdf: alumno sin plan/programa.")
        return None

    programa = plan.programa

    ctx = {
        "alumno": alumno,
        "plan": plan,
        "programa": programa,
        "institucion": {
            "nombre": "Instituto Universitario de Alta Formación",
            "rfc": "—",
            "cct": "23PSU0064H",
            "direccion": "Blvd. Kukulkán Km 3.5, Plaza Nautilus Int. 53, Cancún, Q.R.",
            "ciudad": "México",
            "telefono": "998 939 4481",
            "email": "cadministrativa@iuaf.edu.mx",
        },
        "hoy": timezone.localdate(),
        "grupo_codigo": getattr(plan, "grupo", "") or "",
        "fecha_inicio": getattr(plan, "inicio_programa", None),
        "fecha_fin": getattr(plan, "fin_programa", None),
        "meses_programa": getattr(plan, "meses_programa", None),
        "inscripcion": getattr(plan, "precio_inscripcion", None),
        "reinscripcion": getattr(plan, "precio_reinscripcion", None),
        "colegiatura_mensual": getattr(plan, "precio_final", None) or getattr(plan, "precio_colegiatura", None),
        "meses_pago": getattr(plan, "meses_programa", None),
        "titulacion": getattr(programa, "titulacion", None) if programa else None,
        "etiqueta_beca": (plan.financiamiento.beca if getattr(plan, "financiamiento_id", None) else None),
        "asistencia": "Viernes y Sábado",
        "horario": "V: 17 a 21 hrs · S: 9 a 14 hrs",
        "duracion_texto": f"{getattr(plan, 'meses_programa', '—')} MESES",
        "pdf_mode": True,
    }

    # Render HTML
    html = render_to_string("reportes/carta_inscripcion.html", ctx, request=request)

    # Base href para que src="/static/..." funcione
    base_url = request.build_absolute_uri("/")
    if "<head>" in html:
        html = html.replace("<head>", f'<head><base href="{base_url}">', 1)
    else:
        html = f'<base href="{base_url}">{html}'

    # Carpeta destino
    if getattr(settings, "STATICFILES_DIRS", None):
        static_write_root = settings.STATICFILES_DIRS[0]
    else:
        static_write_root = os.path.join(settings.BASE_DIR, "static")

    dest_dir = os.path.join(static_write_root, "iuaf", "bienvenida", "pdf")
    os.makedirs(dest_dir, exist_ok=True)

    student_number = str(getattr(alumno, "numero_estudiante", "") or f"alumno_{alumno.pk}")
    filepath = os.path.abspath(os.path.join(dest_dir, f"{student_number}.pdf"))

    # Si ya existe, no lo volvemos a crear (devuelve el existente)
    if os.path.isfile(filepath):
        _dbg(f"generar_carta_inscripcion_pdf: ya existe → {filepath}")
        return filepath

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.set_content(html, wait_until="networkidle")
            page.pdf(
                path=filepath,
                print_background=True,
                format="Letter",
                margin={"top": "0.55in", "right": "0.55in", "bottom": "0.55in", "left": "0.55in"},
            )
            browser.close()
        _dbg(f"generar_carta_inscripcion_pdf: creado OK → {filepath}")
        return filepath
    except Exception as e:
        _dbg(f"generar_carta_inscripcion_pdf: ERROR → {e}\n{traceback.format_exc()}")
        return None
# =========================
# Vista principal
# =========================
@login_required
def enviar_bienvenida_estatica(request, alumno_id):
    _dbg(f"== INICIO enviar_bienvenida_estatica alumno_id={alumno_id} ==")

    alumno = get_object_or_404(Alumno, pk=alumno_id)
    plan = getattr(alumno, "informacionEscolar", None)
    force = request.GET.get("force") in ("1", "true", "True")
    _dbg(f"force={force}, alumno.email={alumno.email}, alumno.email_institucional={alumno.email_institucional}")

    if plan and getattr(plan, "bienvenida_enviada", False) and not force:
        _dbg("Bienvenida ya enviada previamente; abortando (sin force).")
        messages.info(request, "Este alumno ya tiene marcada la bienvenida como enviada. Usa ?force=1 para reenviar.")
        return redirect("alumnos_detalle", pk=alumno.pk)

    to_email = (alumno.email or alumno.email_institucional or "").strip()
    if not to_email:
        _dbg("SIN correo destino.")
        messages.error(request, "El alumno no tiene correo.")
        return redirect("alumnos_detalle", pk=alumno.pk)

    subject = "Bienvenida al Instituto Universitario de Alta Formación (IUAF)"
    ctx_mail = {
        "alumno": alumno,
        "facebook_url": "https://www.facebook.com/IuafOficial/",
        "instagram_url": "https://www.instagram.com/iuafoficial/",
    }

    html_mail = render_to_string("emails/bienvenida_estatica.html", ctx_mail, request=request)
    text_mail = render_to_string("emails/bienvenida_estatica.txt", ctx_mail, request=request)

    msg = EmailMultiAlternatives(
        subject=subject,
        body=text_mail,
        from_email=None,
        to=[to_email],
    )
    msg.mixed_subtype = "related"
    msg.attach_alternative(html_mail, "text/html")
    _dbg("EmailMultiAlternatives creado y HTML adjuntado.")

    # Imágenes inline
    logo_path = finders.find("iuaf/iuaf-logo3.png")
    _dbg(f"logo_path={logo_path}")
    if logo_path:
        try:
            with open(logo_path, "rb") as f:
                img = MIMEImage(f.read(), _subtype="png")
                img.add_header("Content-ID", "<logo-iuaf>")
                img.add_header("Content-Disposition", "inline", filename="iuaf-logo3.png")
                msg.attach(img)
            _dbg("Logo inline adjuntado.")
        except Exception as e:
            _dbg(f"Error adjuntando logo: {e}\n{traceback.format_exc()}")

    hero_path = finders.find("iuaf/imagencorreo.png")
    _dbg(f"hero_path={hero_path}")
    if hero_path:
        try:
            with open(hero_path, "rb") as f:
                img = MIMEImage(f.read(), _subtype="png")
                img.add_header("Content-ID", "<hero-iuaf>")
                img.add_header("Content-Disposition", "inline", filename="imagencorreo.png")
                msg.attach(img)
            _dbg("Hero inline adjuntado.")
        except Exception as e:
            _dbg(f"Error adjuntando hero: {e}\n{traceback.format_exc()}")

    docs_attached = 0

    # Adjuntos por PROGRAMA
    program_code = ""
    if plan and getattr(plan, "programa", None) and getattr(plan.programa, "codigo", None):
        program_code = (plan.programa.codigo or "").strip()
    _dbg(f"program_code='{program_code}'")

    def attach_dir(rel_dir):
        nonlocal docs_attached
        files = collect_program_docs(rel_dir)
        _dbg(f"Adjuntando {len(files)} archivo(s) de '{rel_dir}'…")
        for abs_path, download_name, mime in files:
            try:
                size = os.path.getsize(abs_path)
                _dbg(f"Adjuntando '{download_name}' ({size} bytes, {mime})")
                with open(abs_path, "rb") as f:
                    msg.attach(download_name, f.read(), mime)
                    docs_attached += 1
            except Exception as e:
                _dbg(f"No se pudo adjuntar {download_name}: {e}\n{traceback.format_exc()}")
                messages.warning(request, f"No se pudo adjuntar {download_name}: {e}")

    if program_code:
        rel_dir = os.path.join("iuaf", "bienvenida", program_code)
        if collect_program_docs(rel_dir):
            attach_dir(rel_dir)
        else:
            _dbg(f"No hay docs en '{rel_dir}', usando 'comun'.")
            messages.warning(request, f"No se encontraron documentos en: {rel_dir}")
            attach_dir(os.path.join("iuaf", "bienvenida", "comun"))
    else:
        _dbg("Sin program_code; no se adjuntan docs específicos.")
        messages.warning(request, "El alumno no tiene programa/código de programa; no se adjuntaron documentos específicos.")

    # ========= Adjuntar CARTA desde STATIC_ROOT/staticfiles =========
    def _safe_student_number(al):
        sn = str(getattr(al, "numero_estudiante", "") or f"alumno_{al.pk}").strip()
        return "".join(ch for ch in sn if ch.isalnum() or ch in ("-", "_"))

    stored_path = None  # para evitar duplicados al buscar PDFs adicionales
    try:
        static_write_root = _static_write_root()  # <- usa STATIC_ROOT si existe
        pdf_dir = static_write_root / "iuaf" / "bienvenida" / "pdf"
        pdf_dir.mkdir(parents=True, exist_ok=True)
        _dbg(f"pdf_dir={pdf_dir} (exists={pdf_dir.exists()})")

        student_number = _safe_student_number(alumno)
        stored_filename = f"{student_number}.pdf"
        candidate_path = (pdf_dir / stored_filename).resolve()
        _dbg(f"Buscando carta ya creada: {candidate_path}")
        _dbg(f"exists={candidate_path.exists()}; size={candidate_path.stat().st_size if candidate_path.exists() else '—'}")

        if candidate_path.exists():
            try:
                # Nombre “bonito” para el adjunto
                def clean(s): return " ".join((s or "").split())
                safe_name = "_".join(filter(None, [
                    clean(getattr(alumno, "apellido_p", None)),
                    clean(getattr(alumno, "apellido_m", None)),
                    clean(getattr(alumno, "nombre", None)),
                ])).replace(" ", "_") or str(alumno.pk)

                attach_name = f"Carta_Inscripcion_{safe_name}.pdf"
                with open(candidate_path, "rb") as f:
                    msg.attach(attach_name, f.read(), "application/pdf")
                docs_attached += 1
                stored_path = str(candidate_path)  # para evitar duplicados luego
                _dbg(f"Carta existente adjuntada como '{attach_name}'.")
            except Exception as e:
                _dbg(f"No se pudo adjuntar carta existente: {e}\n{traceback.format_exc()}")
                messages.warning(request, f"No se pudo adjuntar carta existente: {e}")
        else:
            _dbg("No existe carta previa; se continuará sin generar ni adjuntar carta.")
            messages.info(request, "No se adjuntó carta de inscripción porque no existe el PDF previo para este alumno.")
    except Exception as e:
        _dbg(f"ERROR comprobando/adjuntando carta existente: {e}\n{traceback.format_exc()}")
        messages.warning(request, f"Error al verificar/adjuntar la carta existente: {e}")

    # Adjuntar OTROS PDFs del alumno (que contengan el número) sin duplicar la carta
    try:
        static_write_root = _static_write_root()
        pdf_dir = static_write_root / "iuaf" / "bienvenida" / "pdf"
        student_number = _safe_student_number(alumno)

        _dbg(f"Buscando PDFs adicionales en {pdf_dir} para student_number='{student_number}'")
        if pdf_dir.exists():
            names = os.listdir(pdf_dir)
            _dbg(f"PDFs en carpeta: {names}")
            for fname in names:
                if not fname.lower().endswith(".pdf"):
                    continue
                if student_number not in fname:
                    continue
                fpath = (pdf_dir / fname).resolve()
                # Evitar duplicar la carta ya adjuntada
                if stored_path and os.path.normcase(str(fpath)) == os.path.normcase(stored_path):
                    _dbg(f"Omitiendo (ya se adjuntó carta): {fname}")
                    continue
                try:
                    size = os.path.getsize(fpath)
                    _dbg(f"Adjuntando PDF adicional '{fname}' ({size} bytes).")
                    with open(fpath, "rb") as f:
                        msg.attach(fname, f.read(), "application/pdf")
                        docs_attached += 1
                except Exception as e:
                    _dbg(f"No se pudo adjuntar PDF adicional '{fname}': {e}\n{traceback.format_exc()}")
                    messages.warning(request, f"No se pudo adjuntar PDF adicional '{fname}': {e}")
        else:
            _dbg("No existe la carpeta de PDFs adicionales.")
            messages.info(request, "No existe la carpeta static/iuaf/bienvenida/pdf para buscar PDFs adicionales.")
    except Exception as e:
        _dbg(f"ERROR buscando/adjuntando PDFs adicionales: {e}\n{traceback.format_exc()}")
        messages.warning(request, f"Error al buscar/adjuntar PDFs adicionales del alumno: {e}")

    # Resumen antes de enviar
    try:
        attach_count = len(getattr(msg, "attachments", []))
    except Exception:
        attach_count = "desconocido"
    _dbg(f"Total adjuntos contados por msg.attachments: {attach_count} (docs_attached contador: {docs_attached})")

    # Envío
    try:
        _dbg("Enviando correo…")
        sent_count = msg.send()
        _dbg(f"send() retornó {sent_count}")
        if sent_count > 0 and plan:
            plan.bienvenida_enviada = True
            plan.bienvenida_enviada_en = timezone.now()
            plan.bienvenida_enviada_por = request.user
            plan.save(update_fields=["bienvenida_enviada", "bienvenida_enviada_en", "bienvenida_enviada_por"])

        if sent_count > 0:
            ok_msg = f"Correo de bienvenida enviado a {to_email}."
            if docs_attached:
                ok_msg += f" Adjuntos: {docs_attached}."
            messages.success(request, ok_msg)
        else:
            messages.error(request, "El backend de correo no reportó envíos.")
    except Exception as e:
        _dbg(f"ERROR en envío de correo: {e}\n{traceback.format_exc()}")
        messages.error(request, f"No se pudo enviar el correo: {e}")

    _dbg("== FIN enviar_bienvenida_estatica ==")
    return redirect("alumnos_detalle", pk=alumno.pk)




#############################################################################################################################################

@login_required
def expediente_maestria_view(request, alumno_id):
    alumno = get_object_or_404(Alumno, pk=alumno_id)
    plan = getattr(alumno, "informacionEscolar", None)

    if not plan or not plan.programa_id:
        messages.error(request, "El alumno no tiene plan/programa asignado.")
        return redirect("alumnos_detalle", pk=alumno.pk)

    # Requisitos activos del programa, incluyendo tipo (con orden/presentación/observaciones)
    reqs = (
        plan.requisitos_documentales()  # ya hace select_related("tipo")
        .order_by("tipo__orden", "tipo__nombre")
    )
    # Documentos subidos por tipo
    por_tipo = plan.documentos_por_tipo()

    rows = []
    consecutivo = 1
    for req in reqs:
        tipo = req.tipo
        subidos = len(por_tipo.get(tipo.id, []))
        entrego = subidos >= (req.minimo or 1)  # cumple mínimo

        rows.append({
            "num": consecutivo,
            "descripcion": tipo.nombre,
            "presentacion": tipo.presentacion or "",
            "entrego_si": entrego,
            "entrego_no": not entrego,
            "observaciones": tipo.observaciones or "",
        })
        consecutivo += 1

    ctx = {
        "alumno": alumno,
        "plan": plan,
        "programa": plan.programa,
        "rows": rows,
        # Cabeceras opcionales para el reporte
        "titulo": f"EXPEDIENTE DE INGRESO A {plan.programa.nombre} CON ESTUDIOS EN MÉXICO",
        "subtitulo": f"Programa: {plan.programa.codigo} — {plan.programa.nombre}" if plan.programa else "",
    }

    # Si quieres PDF más adelante, aquí puedes checar ?format=pdf y renderizar con WeasyPrint
    return render(request, "reportes/EXPEDIENTE DE INGRESO.html", ctx)
################################################################################################
# alumnos/views.py
import os

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils import timezone



from .models import Alumno


@login_required
def carta_inscripcion_view(request, alumno_id):
    alumno = get_object_or_404(Alumno, pk=alumno_id)
    plan = getattr(alumno, "informacionEscolar", None)

    if not plan or not plan.programa_id:
        messages.error(request, "El alumno no tiene plan/programa asignado.")
        return redirect("alumnos_detalle", pk=alumno.pk)

    programa = plan.programa

    ctx = {
        "alumno": alumno,
        "plan": plan,
        "programa": programa,
        "institucion": {
            "nombre": "Instituto Universitario de Alta Formación",
            "rfc": "—",
            "cct": "23PSU0064H",
            "direccion": "Blvd. Kukulkán Km 3.5, Plaza Nautilus Int. 53, Cancún, Q.R.",
            "ciudad": "México",
            "telefono": "998 939 4481",
            "email": "cadministrativa@iuaf.edu.mx",
        },
        "hoy": timezone.localdate(),
        "grupo_codigo": plan.grupo or "",
        "fecha_inicio": plan.inicio_programa,
        "fecha_fin": plan.fin_programa,
        "meses_programa": plan.meses_programa,
        "inscripcion": plan.precio_inscripcion,
        "reinscripcion": plan.precio_reinscripcion,
        "colegiatura_mensual": plan.precio_final or plan.precio_colegiatura,
        "meses_pago": plan.meses_programa,
        "titulacion": programa.titulacion if programa else None,
        "etiqueta_beca": (plan.financiamiento.beca if plan.financiamiento_id else None),
        "asistencia": "",
        "horario": "",
        "duracion_texto": f"{plan.meses_programa or '—'} MESES",
        "pdf_mode": False,
    }
    return render(request, "reportes/carta_inscripcion.html", ctx)

##########################################################################################
from pathlib import Path
import os, traceback, logging, re
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.template.loader import render_to_string
from django.utils import timezone
from django.conf import settings
from django.contrib.staticfiles import finders


logger = logging.getLogger(__name__)

# --- Helpers --------------------------------------------------------------

from pathlib import Path
from django.conf import settings
import os

def _static_write_root() -> Path:
    """
    Devuelve la carpeta donde ESCRIBIR/BUSCAR artefactos estáticos generados.
    Prioriza STATIC_ROOT (p.ej. .../staticfiles). Si no hay, usa STATICFILES_DIRS[0].
    Fallback: BASE_DIR/static.
    """
    # 1) STATIC_ROOT (salida de collectstatic)
    root = getattr(settings, "STATIC_ROOT", None)
    if root:
        p = Path(root)
        p.mkdir(parents=True, exist_ok=True)
        return p

    # 2) STATICFILES_DIRS[0] (fuente en desarrollo)
    sfd = getattr(settings, "STATICFILES_DIRS", None)
    if sfd and len(sfd) > 0:
        p = Path(sfd[0])
        p.mkdir(parents=True, exist_ok=True)
        return p

    # 3) Fallback
    p = Path(settings.BASE_DIR) / "static"
    p.mkdir(parents=True, exist_ok=True)
    return p

def _pisa_link_callback(uri, rel):
    """
    Convierte URIs de la plantilla (static/media/http) en rutas de archivo locales
    para que xhtml2pdf (reportlab) pueda leer imágenes y CSS.
    """
    # MEDIA
    media_url = getattr(settings, "MEDIA_URL", "")
    media_root = getattr(settings, "MEDIA_ROOT", "")
    if media_url and uri.startswith(media_url):
        path = os.path.join(media_root, uri.replace(media_url, "").lstrip("/"))
        return path

    # STATIC: buscar con finders para respetar pipeline de staticfiles
    static_url = getattr(settings, "STATIC_URL", "")
    if static_url and uri.startswith(static_url):
        relpath = uri.replace(static_url, "").lstrip("/")
        found = finders.find(relpath)
        if isinstance(found, (list, tuple)):
            found = found[0]
        # Si no lo encuentra, intentar construir relativo al root
        if not found:
            candidate = _static_write_root() / relpath
            if candidate.exists():
                return str(candidate)
        return found or relpath

    # URLs absolutas http(s): xhtml2pdf puede intentar descargarlas (no recomendado)
    if uri.startswith("http://") or uri.startswith("https://"):
        return uri

    # Rutas absolutas del sistema
    if os.path.isabs(uri) and os.path.exists(uri):
        return uri

    # Último recurso: devolver tal cual
    return uri

# (Opcional) Si en tu HTML llegan variables CSS tipo var(--line), puedes sanear:
CSS_VAR_MAP = {
    "--brand": "#6f42c1",
    "--brand-2": "#8a63d2",
    "--ink": "#0f172a",
    "--muted": "#6b7280",
    "--line": "#e5e7eb",
    "--bg": "#f6f7fb",
    "--panel": "#ffffff",
    "--accent": "#16a34a",
    "--accent-ink": "#064e3b",
    "--ink-2": "#111827",
}
_VAR_RE = re.compile(r"var\(\s*(--[a-zA-Z0-9_-]+)\s*(?:,\s*([^)]+))?\)")

def _replace_css_vars(html: str) -> str:
    def _sub(m):
        name = m.group(1)
        fallback = (m.group(2) or "").strip()
        val = CSS_VAR_MAP.get(name)
        if val:
            return val
        return fallback or "#000000"
    return _VAR_RE.sub(_sub, html)

# --- Vista ---------------------------------------------------------------

@login_required
def carta_inscripcion_pdf_view(request, alumno_id):
    print("[PDF/PISA] INICIO vista carta_inscripcion_pdf_view")
    alumno = get_object_or_404(Alumno, pk=alumno_id)
    plan = getattr(alumno, "informacionEscolar", None)
    if not plan or not plan.programa_id:
        messages.error(request, "El alumno no tiene plan/programa asignado.")
        return redirect(request.META.get("HTTP_REFERER") or "alumnos_detalle", pk=alumno.pk)

    programa = plan.programa
    ctx = {
        "alumno": alumno,
        "plan": plan,
        "programa": programa,
        "institucion": {
            "nombre": "Instituto Universitario de Alta Formación",
            "rfc": "—",
            "cct": "23PSU0064H",
            "direccion": "Blvd. Kukulkán Km 3.5, Plaza Nautilus Int. 53, Cancún, Q.R.",
            "ciudad": "México",
            "telefono": "998 939 4481",
            "email": "cadministrativa@iuaf.edu.mx",
        },
        "hoy": timezone.localdate(),
        "grupo_codigo": plan.grupo or "",
        "fecha_inicio": plan.inicio_programa,
        "fecha_fin": plan.fin_programa,
        "meses_programa": plan.meses_programa,
        "inscripcion": plan.precio_inscripcion,
        "reinscripcion": plan.precio_reinscripcion,
        "colegiatura_mensual": plan.precio_final or plan.precio_colegiatura,
        "meses_pago": plan.meses_programa,
        "titulacion": programa.titulacion if programa else None,
        "etiqueta_beca": (plan.financiamiento.beca if plan.financiamiento_id else None),
        "asistencia": "Viernes y Sábado",
        "horario": "V: 17 a 21 hrs · S: 9 a 14 hrs",
        "duracion_texto": f"{plan.meses_programa or '—'} MESES",
        "pdf_mode": True,  # evita CSS/JS externos en el PDF
    }

    # 1) Render HTML
    try:
        html = render_to_string("reportes/carta_inscripcion.html", ctx, request=request)
        print("[PDF/PISA] HTML renderizado OK (len)", len(html))
    except Exception as e:
        logger.exception("[PDF/PISA] Error render_to_string")
        messages.error(request, f"Error renderizando plantilla: {e}")
        return redirect(request.META.get("HTTP_REFERER") or "alumnos_detalle", pk=alumno.pk)

    # (Opcional) Sanea variables CSS si quedara alguna var(--xxx)
    html = _replace_css_vars(html)

    # 2) Carpeta de salida dentro de STATIC (lo que pediste)
    static_root = _static_write_root()
    out_dir = static_root / "iuaf" / "bienvenida" / "pdf"
    out_dir.mkdir(parents=True, exist_ok=True)

    # 2.a) Guardar HTML DEBUG en la misma carpeta
    #debug_html = out_dir / f"DEBUG_{alumno.numero_estudiante}.html"
    #try:
    #    debug_html.write_text(html, encoding="utf-8")
    #    print(f"[PDF/PISA] HTML debug: {debug_html}")
    #except Exception as e:
    #    print("[PDF/PISA][WARN] No pudo guardar HTML debug:", e)

    # 3) Generar PDF con xhtml2pdf
    out_path = out_dir / f"{alumno.numero_estudiante}.pdf"
    print(f"[PDF/PISA] Escribirá en: {out_path}")

    try:
        with open(out_path, "wb") as f:
            pisa_status = pisa.CreatePDF(
                src=html,
                dest=f,
                link_callback=_pisa_link_callback,
                encoding="utf-8",
            )
        if pisa_status.err:
            print("[PDF/PISA][ERROR] pisa err=True")
            messages.error(request, "No se pudo generar el PDF (pisa). Revisa HTML/CSS.")
        else:
            print("[PDF/PISA] PDF generado OK")
            messages.success(request, f"PDF guardado como {out_path.name}.")
    except Exception as e:
        tb = traceback.format_exc()
        print("[PDF/PISA][ERROR] Excepción creando PDF:", e)
        print("[PDF/PISA][TRACEBACK]\n", tb)
        messages.error(request, f"No se pudo generar el PDF: {e}")

    # 4) Regresar a la misma página
    return redirect(request.META.get("HTTP_REFERER") or "alumnos_detalle", pk=alumno.pk)
##########################################################

# alumnos/views.py
from django.views.decorators.http import require_POST
from django.core.mail import EmailMessage
from django.http import JsonResponse, HttpResponseForbidden
from django.utils.text import slugify

@login_required
@require_POST
def enviar_recibo_email_con_pdf(request, pago_id):
    # Valida permisos mínimos (ajusta a tu lógica)
    if not (request.user.is_staff or request.user.is_superuser):
        return HttpResponseForbidden("No autorizado.")

    pago = get_object_or_404(PagoDiario.objects.select_related("alumno"), pk=pago_id)
    alumno = pago.alumno

    # PDF subido desde el navegador (form-data key: 'recibo')
    pdf_file = request.FILES.get("recibo")
    if not pdf_file:
        return JsonResponse({"ok": False, "error": "No se recibió el archivo PDF."}, status=400)

    # Chequeo básico
    ct = pdf_file.content_type or ""
    if "pdf" not in ct:
        return JsonResponse({"ok": False, "error": "El archivo no parece ser un PDF."}, status=400)

    # Destinatario
    to_email = (alumno.email or alumno.email_institucional or "").strip() or pago.email or ""
    if not to_email:
        return JsonResponse({"ok": False, "error": "El alumno no tiene correo."}, status=400)

    # Asunto / cuerpo
    asunto = f"Recibo de pago #{pago.folio or pago.pk}"
    cuerpo = (
        f"Hola {alumno.nombre or 'Alumno'},\n\n"
        f"Te compartimos tu recibo de pago.\n\n"
        f"Folio: {pago.folio or pago.pk}\n"
        f"Fecha: {pago.fecha.strftime('%d/%m/%Y') if pago.fecha else '—'}\n"
        f"Monto: $ {pago.monto or '0.00'}\n\n"
        f"Saludos."
    )

    # Nombre del adjunto
    base = slugify(f"recibo_{pago.folio or pago.pk}")
    filename = f"{base}.pdf"

    # Enviar
    msg = EmailMessage(
        subject=asunto,
        body=cuerpo,
        from_email=None,   # usa DEFAULT_FROM_EMAIL
        to=[to_email],
    )
    msg.attach(filename, pdf_file.read(), "application/pdf")
    sent = msg.send()

    if sent:
        return JsonResponse({"ok": True, "msg": f"Correo enviado a {to_email}."})
    else:
        return JsonResponse({"ok": False, "error": "El backend de correo no reportó envíos."}, status=500)
