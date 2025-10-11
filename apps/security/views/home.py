
from django.views.generic import TemplateView
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from apps.security.components.menu_module import MenuModule
from apps.security.components.group_session import UserGroupSession
# from apps.core.models import Student, Enrollment, Assignment, Submission, Progress
from django.db.models import Avg, Count, Q


@method_decorator(login_required, name='dispatch')
class ModuloTemplateView(TemplateView):
    template_name = 'home.html'
   
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = "Studer - Módulos"
        context["title1"] = "Bienvenido a tu plataforma educativa Studer"
        
        # Configurar sesión de grupo si no existe
        user_session = UserGroupSession(self.request)
        user_session.set_group_session()
        
        # Aquí puedes agregar más contexto relevante para Studer si lo necesitas
        MenuModule(self.request).fill(context)
        # Extraer los menús "Herramientas" y "Sidebar" si existen
        herramientas_menu = None
        sidebar_menu = None
        for menu_item in context.get('menu_list', []):
            menu_name = getattr(menu_item['menu'], 'name', '').lower()
            if menu_name == 'herramientas':
                herramientas_menu = menu_item
            if menu_name == 'sidebar':
                sidebar_menu = menu_item
        context['herramientas_menu'] = herramientas_menu
        context['sidebar_menu'] = sidebar_menu

        
        return context