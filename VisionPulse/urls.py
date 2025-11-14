"""
URL configuration for visionpulse project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    # URLs principales - Landing y dashboard
    path('', include('apps.security.urls')),
    # URLs de la app security (también bajo /security/) - Comentado para evitar duplicado de namespace
    # path('security/', include('apps.security.urls')),
    # path('frontend/', include('apps.frontend.urls')),  # Comentado temporalmente
    path('monitoring/', include('apps.monitoring.urls')),
    path('exercises/', include('apps.exercises.urls')),
    path('reports/', include('apps.reports.urls')),
    # URLs de autenticación social
    path('auth/', include('social_django.urls', namespace='social')),
    path("__reload__/", include("django_browser_reload.urls")),
]
# Servir archivos media en desarrollo
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
