from apps.security.models import Menu

class SidebarMenuMixin:
    """
    Un Mixin para Class-Based Views que inyecta la estructura del menú del sidebar
    en el contexto de la plantilla, basándose en los grupos y permisos del usuario.
    """
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Inicia una estructura vacía si el usuario no está autenticado
        sidebar_structure = []
        
        if self.request.user.is_authenticated:
            # Obtenemos los grupos a los que pertenece el usuario
            user_groups = self.request.user.groups.all()

            # Consultamos los menús que tienen módulos activos a los que el usuario tiene acceso
            # prefetch_related('modules') optimiza la consulta para evitar N+1 queries
            accessible_menus = Menu.objects.prefetch_related('modules').filter(
                modules__group_permissions__group__in=user_groups,
                modules__is_active=True
            ).distinct().order_by('order')

            for menu in accessible_menus:
                menu_item = {
                    'name': menu.name,
                    'icon': menu.icon,
                    'modules': []
                }
                
                # Usamos los módulos ya precargados por prefetch_related
                for module in sorted(menu.modules.all(), key=lambda m: m.order):
                    # Verificamos si el módulo está activo y si el usuario tiene permiso
                    has_permission = module.is_active and module.group_permissions.filter(group__in=user_groups).exists()
                    
                    # Evitamos duplicados (aunque distinct() en el query principal ayuda)
                    is_already_added = any(m['url'] == module.url for m in menu_item['modules'])

                    if has_permission and not is_already_added:
                        menu_item['modules'].append({
                            'name': module.name,
                            'url': module.url,  # Guardamos el nombre de la URL para usarlo en la plantilla
                            'icon': module.icon
                        })
                
                # Solo añadimos el menú al sidebar si contiene al menos un módulo accesible
                if menu_item['modules']:
                    sidebar_structure.append(menu_item)

        context['sidebar_menu'] = sidebar_structure
        return context
