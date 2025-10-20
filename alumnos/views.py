from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django import forms
from .models import Alumno, DocumentosAlumno, Programa
from django.contrib.auth.models import User, Group

from django.contrib import messages
from django.contrib.auth.models import User
from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError
from .models import Cargo, ClipPaymentOrder, Pago
from .models import Financiamiento

from django.utils import timezone
from django.http import JsonResponse, Http404
from datetime import date

from .forms import DocumentosAlumnoForm, InformacionEscolarForm

from django.db.models import Q
from .models import  Pais, Estado

from django.contrib.auth.decorators import login_required

from django.contrib.auth.decorators import user_passes_test


from alumnos.permisos import  user_can_edit_alumno, user_can_view_alumno

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
            alumno = form.save(commit=False)
            alumno.numero_estudiante = siguiente_numero_estudiante()
            alumno.save()
            messages.success(request, "Alumno creado correctamente.")
            return redirect("alumnos_detalle", pk=alumno.pk)
    else:
        form = AlumnoForm(crear=True, request=request)

    return render(request, "alumnos/editar_alumno.html", {
        "form": form,
        "alumno": None,
        "modo": "crear",
        # opcional: una vista previa NO reservada
        # "preview_numero": (ContadorAlumno.objects.first().ultimo_numero + 1) if ContadorAlumno.objects.exists() else 1,
    })
####################################################################################
# views.py (o donde tengas alumnos_editar)
from django.db.models import Sum
from alumnos.models import Alumno, PagoDiario
from django.http import HttpResponseForbidden
# Mantén este decorador si solo staff puede editar:
@admin_required
# Si quieres staff o admisiones, usa este en su lugar:
# @staff_or_admisiones_required
def alumnos_editar(request, pk):
    alumno = get_object_or_404(Alumno, pk=pk)

    if not user_can_edit_alumno(request.user, alumno):
        return HttpResponseForbidden("No tienes permiso para editar este alumno.")

    plan_instance = alumno.informacionEscolar  # puede ser None
    docs_instance, _ = DocumentosAlumno.objects.get_or_create(alumno=alumno)

    # Pagos del alumno para el panel lateral
    pagos_qs = PagoDiario.objects.filter(alumno=alumno).order_by("-fecha", "-id")
    pagos_total = pagos_qs.aggregate(total=Sum("monto"))["total"] or 0

    if request.method == "POST":
        form = AlumnoForm(request.POST, instance=alumno, request=request)
        form_info = InformacionEscolarForm(
            request.POST,
            instance=plan_instance,
            readonly_prices=True,     # bloque “Precios y reinscripciones” solo lectura
            request=request,          # para chequear grupos de estatus
        )
        docs_form = DocumentosAlumnoForm(request.POST, request.FILES, instance=docs_instance)

        if form.is_valid() and form_info.is_valid() and docs_form.is_valid():
            alumno = form.save()

            # Crea/actualiza plan escolar
            plan = form_info.save()
            if not alumno.informacionEscolar_id:
                alumno.informacionEscolar = plan
                alumno.save(update_fields=["informacionEscolar"])

            # Documentos
            docs_form.save()

            messages.success(request, "Alumno, plan y documentos actualizados.")
            return redirect("alumnos_detalle", pk=alumno.pk)
        else:
            messages.error(request, "Revisa los errores del formulario.")
    else:
        form = AlumnoForm(instance=alumno, request=request)
        form_info = InformacionEscolarForm(
            instance=plan_instance,
            readonly_prices=True,     # también en GET para que salgan deshabilitados
            request=request,
        )
        docs_form = DocumentosAlumnoForm(instance=docs_instance)

    return render(
        request,
        "alumnos/editar_alumno.html",
        {
            "form": form,
            "form_info": form_info,
            "docs_form": docs_form,
            "alumno": alumno,
            "modo": "editar",
            "pagos": pagos_qs,
            "pagos_total": pagos_total,
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
# estudiantes()
@login_required
def estudiantes(request):
    q = (request.GET.get("q") or "").strip()

    qs = (
        Alumno.for_user(request.user)  # <- AQUÍ
        .select_related(
            "pais", "estado",
            "informacionEscolar",
            "informacionEscolar__programa",
            "informacionEscolar__sede",
            "user", "documentos",
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

    return render(request, "panel/all_orders.html", {"alumnos": qs, "q": q})


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
@login_required
def alumnos_detalle(request, pk):
    # Cargamos el alumno con todo lo necesario para evitar N+1
    alumno = get_object_or_404(
        Alumno.objects.select_related(
            "pais",
            "estado",
            "informacionEscolar",
            "informacionEscolar__programa",
            "informacionEscolar__sede",
        ),
        pk=pk,
    )

    # ==========================
    # Permisos de visualización
    # ==========================
    user = request.user
    can_view = False

    if user.is_superuser:
        can_view = True
    else:
        # Si es del grupo "admisiones": solo ve alumnos que él creó
        if user.groups.filter(name="admisiones").exists():
            can_view = (alumno.created_by_id == user.id)
        else:
            # Resto de usuarios: por sedes asignadas
            profile = getattr(user, "profile", None)
            if profile:
                # sede del alumno (defensivo si no hay informacionEscolar)
                sede_id = getattr(getattr(alumno, "informacionEscolar", None), "sede_id", None)
                if sede_id and profile.sedes.filter(id=sede_id).exists():
                    can_view = True

    if not can_view:
        return HttpResponseForbidden("No tienes permiso para ver este alumno.")

    # ==========================
    # Datos relacionados (pagos, cargos)
    # ==========================
    pagos = (
        PagoDiario.objects
        .filter(alumno=alumno)
        .order_by("-fecha", "-id")
    )
    pagos_total = pagos.aggregate(total=Sum("monto"))["total"] or 0
    pagos_total = round(pagos_total, 2)

    cargos = (
        Cargo.objects
        .filter(alumno=alumno)
        .select_related("concepto")
        .order_by("-fecha_cargo", "-id")
    )
    cargos_pendientes = cargos.filter(pagado=False)

    # ==========================
    # Render
    # ==========================
    return render(
        request,
        "alumnos/detalle.html",
        {
            "alumno": alumno,
            "pagos": pagos,
            "pagos_total": pagos_total,
            "cargos": cargos,
            "cargos_pendientes": cargos_pendientes,
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
def documentos_alumno_editar(request, numero_estudiante):
    alumno = get_object_or_404(Alumno, pk=numero_estudiante)
    docs, _ = DocumentosAlumno.objects.get_or_create(alumno=alumno)

    if request.method == "POST":
        form = DocumentosAlumnoForm(request.POST, request.FILES, instance=docs)
        if form.is_valid():
            form.save()
            messages.success(request, "Documentos actualizados.")
            return redirect("alumnos_detalle", alumno.pk)  # ajusta el nombre de tu url
    else:
        form = DocumentosAlumnoForm(instance=docs)

    return render(request, "alumnos/documentos_form.html", {
        "alumno": alumno,
        "form": form,
    })
###########################################################################################################
from django.utils.decorators import method_decorator
from django.views.generic import ListView
from .models import PagoDiario

@method_decorator(login_required, name="dispatch")
class PagoDiarioListView(ListView):
    model = PagoDiario
    template_name = "alumnos/pagos_diario_list.html"
    context_object_name = "pagos"
    paginate_by = None  # DataTables pagina en el cliente

    def get_queryset(self):
        qs = (
            PagoDiario.objects
            .select_related("alumno")
            .order_by("-fecha", "-id")
        )

        user = self.request.user
        if not user.is_authenticated:
            return qs.none()

        # ---- Admisiones: solo pagos de sus alumnos
        if user.groups.filter(name="admisiones").exists():
            qs = qs.filter(alumno__created_by=user)
            # Si quieres también limitar por fecha a admisiones,
            # descomenta el bloque de 2 años más abajo.
        else:
            # ---- No superuser: limitar por sedes
            if not user.is_superuser:
                profile = getattr(user, "profile", None)
                if not profile:
                    return qs.none()

                sedes_ids = list(profile.sedes.values_list("id", flat=True))
                if not sedes_ids:
                    return qs.none()

                qs = qs.filter(alumno__informacionEscolar__sede_id__in=sedes_ids)

            # ---- ver_todos_los_pagos
            profile = getattr(user, "profile", None)
            show_all = bool(profile and getattr(profile, "ver_todos_los_pagos", False))

            # ---- Si NO show_all => limitar a últimos 2 años
            if not show_all:
                hace_dos_anios = timezone.now().date() - timedelta(days=730)
                qs = qs.filter(fecha__gte=hace_dos_anios)

        # ---- Búsqueda opcional
        q = (self.request.GET.get("q") or "").strip()
        if q:
            qs = qs.filter(
                Q(alumno__numero_estudiante__icontains=q) |
                Q(alumno__nombre__icontains=q) |
                Q(alumno__apellido_p__icontains=q) |
                Q(alumno__apellido_m__icontains=q) |
                Q(curp__icontains=q) |
                Q(folio__icontains=q) |
                Q(concepto__icontains=q) |
                Q(programa__icontains=q)
            )

        return qs

############################################################################################################

@login_required
def programa_info(request, pk):
    """Devuelve los valores por defecto del programa elegido."""
    try:
        p = Programa.objects.get(pk=pk)
    except Programa.DoesNotExist:
        return JsonResponse({"error": "Programa no encontrado"}, status=404)

    data = {
        "meses_programa": p.meses_programa,
        "precio_colegiatura": str(p.colegiatura),
        "precio_inscripcion": str(p.inscripcion),
        "precio_titulacion": str(p.titulacion),
        "precio_equivalencia": str(p.equivalencia),
        "numero_reinscripciones": 0,  # si tienes un valor base, cámbialo
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
@login_required
def alumnos_documentos_editar(request, pk):
    alumno = get_object_or_404(Alumno, pk=pk)
    # crea si no existe
    docs, _ = DocumentosAlumno.objects.get_or_create(alumno=alumno)

    if request.method == "POST":
        form = DocumentosAlumnoForm(request.POST, request.FILES, instance=docs)
        if form.is_valid():
            form.save()
            messages.success(request, "Documentos actualizados correctamente.")
            # redirige a donde prefieras (detalle del alumno, o quedarse aquí)
            return redirect("alumnos_documentos_editar", pk=alumno.pk)
        else:
            messages.error(request, "Revisa los errores del formulario.")
    else:
        form = DocumentosAlumnoForm(instance=docs)

    return render(request, "alumnos/documentos_form.html", {
        "alumno": alumno,
        "form": form,
    })

###############################################################
@login_required
def documentos_alumnos_lista(request):
    q = (request.GET.get("q") or "").strip()

    base = (
        DocumentosAlumno.objects
        .select_related(
            "alumno",
            "alumno__informacionEscolar",
            "alumno__informacionEscolar__programa",
            "alumno__informacionEscolar__sede",
        )
        .order_by("-fecha_ultima_actualizacion", "alumno__numero_estudiante")
    )

    user = request.user
    if not user.is_authenticated:
        qs = base.none()
    elif user.is_superuser:
        qs = base
    elif user.groups.filter(name="admisiones").exists():
        # Admisiones: solo documentos de sus alumnos
        qs = base.filter(alumno__created_by=user)
    else:
        profile = getattr(user, "profile", None)
        if not profile:
            qs = base.none()
        else:
            sedes_ids = list(profile.sedes.values_list("id", flat=True))
            qs = base.filter(alumno__informacionEscolar__sede_id__in=sedes_ids) if sedes_ids else base.none()

    # Búsqueda opcional
    if q:
        qs = qs.filter(
            Q(alumno__numero_estudiante__icontains=q) |
            Q(alumno__nombre__icontains=q) |
            Q(alumno__apellido_p__icontains=q) |
            Q(alumno__apellido_m__icontains=q) |
            Q(alumno__curp__icontains=q) |
            Q(alumno__email__icontains=q)
        )

    ctx = {"q": q, "documentos": qs}
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