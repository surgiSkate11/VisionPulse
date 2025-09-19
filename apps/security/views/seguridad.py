# === Vistas movidas desde core para uso exclusivo en security ===
from django.shortcuts import render, redirect

def terms(request):
    return render(request, 'core/terms.html')

def privacy(request):
    return render(request, 'core/privacy.html')

def landing_view(request):
    """
    Vista para mostrar la landing page de Studer
    Si el usuario ya está autenticado, redirige a home (security:home)
    """
    if request.user.is_authenticated:
        return redirect("security:home")
    return render(request, 'landing.html')
from django.views.generic import TemplateView
from apps.security.models import Menu  # Ajusta si tu modelo está en otro lugar

from apps.security.components.sidebar_menu_mixin import SidebarMenuMixin

class SeguridadView(SidebarMenuMixin, TemplateView):
    template_name = 'security/profile/security.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # SidebarMenuMixin ya llena menu_list, sidebar_menu y herramientas_menu
        group = context.get('group')
        context['selected_group'] = group.name if group else None
        if not (self.request.user.is_superuser or (group and group.name == "Administrador")):
            context['menu_list'] = []
            context['title'] = 'Acceso denegado'
            context['access_denied'] = True
            return context
        # Buscar el menú llamado 'Seguridad' en el contexto generado
        menu = None
        for m in context.get('menu_list', []):
            if m['menu'].name.lower() == 'seguridad':
                menu = m
                break
        # Solo mostrar el menú Seguridad en el contenido principal, pero NO tocar sidebar_menu
        context['menu_list'] = [menu] if menu else []
        context['title'] = 'Seguridad'
        return context