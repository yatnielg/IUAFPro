from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("allauth.urls")),  # si usas allauth

    #path("", include("alumnos.urls")),
    path("", include(("alumnos.urls", "alumnos"), namespace="alumnos")),
    
    path('cobros/', include('cobros.urls')),
    path("academico/", include("academico.urls")),

    # OAuth2 clásico (authorize, token, revoke, introspect, etc.)
    path("o/", include(("oauth2_provider.urls", "oauth2_provider"), namespace="oauth2_provider")),

    path("lms/", include("lms.urls", namespace="lms")),

    
]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)


""" urlpatterns += [
    path("", include("oauth2_provider.oidc.urls")),   # DOT 3.x
] """