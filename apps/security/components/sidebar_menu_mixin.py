from apps.security.components.menu_module import MenuModule

class SidebarMenuMixin:
    def get_context_data(self, context=None, request=None, **kwargs):
        # Permite uso tanto en CBV como en FBV
        if context is None:
            # CBV: usar super() si está disponible
            try:
                context = super().get_context_data(**kwargs)
            except AttributeError:
                context = kwargs
        else:
            context.update(kwargs)
        # Obtener request
        req = request or getattr(self, 'request', None)
        if req is not None:
            MenuModule(req).fill(context)
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
