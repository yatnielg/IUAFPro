from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django import forms
from .models import Alumno, DocumentosAlumno
from django.contrib.auth.models import User, Group

from django.contrib import messages
from django.contrib.auth.models import User
from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError

from django.utils import timezone
from datetime import date

from .forms import DocumentosAlumnoForm

from django.db.models import Q
from .models import  Pais, Estado

from django.contrib.auth.decorators import login_required
# Create your views here.
####################################################################
# views.py
#from django.shortcuts import redirectt_object_or_404
from django.contrib.auth.decorators import user_passes_test
from .forms import AlumnoForm

def admin_required(view_func):
    return user_passes_test(lambda u: u.is_active and u.is_staff)(view_func)

@admin_required
def alumnos_crear(request):
    if request.method == "POST":
        form = AlumnoForm(request.POST)
        if form.is_valid():
            alumno = form.save()
            messages.success(request, "Alumno creado correctamente.")
            return redirect("alumnos_detalle", pk=alumno.pk)
    else:
        form = AlumnoForm()
    return render(request, "alumnos/editar_alumno.html", {
        "form": form,
        "alumno": None,
        "modo": "crear",
    })

@admin_required
def alumnos_editar(request, pk):
    alumno = get_object_or_404(Alumno, pk=pk)  # pk = numero_estudiante
    if request.method == "POST":
        form = AlumnoForm(request.POST, instance=alumno)
        if form.is_valid():
            form.save()
            messages.success(request, "Alumno actualizado correctamente.")
            return redirect("alumnos_detalle", pk=alumno.pk)
    else:
        form = AlumnoForm(instance=alumno)
    return render(request, "alumnos/editar_alumno.html", {
        "form": form,
        "alumno": alumno,
        "modo": "editar",
    })

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

@login_required
def estudiantes(request):    
    q = request.GET.get("q", "").strip()
    qs = Alumno.objects.all()
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
  
@login_required   
def principal(request):
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
@login_required    
def alumnos_lista(request):
    q = request.GET.get("q", "").strip()
    qs = Alumno.objects.all()
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
    alumno = get_object_or_404(Alumno, pk=pk)
    return render(request, "alumnos/detalle.html", {"alumno": alumno})

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