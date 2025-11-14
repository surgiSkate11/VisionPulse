from datetime import datetime
from django.contrib.auth.models import Group
from django.http import HttpRequest

from apps.security.models import GroupModulePermission, User

class MenuModule:
    def __init__(self, request: HttpRequest):
        # Guarda el request y la ruta actual
        self._request = request
        self._path = self._request.path
        self._current_time = datetime.now()

    def fill(self, data):
        """
        Añade información relevante al diccionario 'data' y a la sesión:
        - Usuario autenticado
        - Fecha y hora actual
        - Lista de grupos del usuario
        - Grupo seleccionado y menús asociados
        """
        data['user'] = self._request.user
        data['date_time'] = self._current_time
        data['date_date'] = self._current_time.date()

        if not self._request.user.is_authenticated:
            return

        # Obtener grupos del usuario una sola vez
        user_groups = self._request.user.groups.all().order_by('id')
        data['group_list'] = user_groups

        # Si no hay grupos, no hay nada más que hacer
        if not user_groups.exists():
            return

        # Determinar el grupo activo
        active_group_id = self._get_active_group_id(user_groups)
        if not active_group_id:
            return

        # Obtener el grupo y sus menús
        try:
            group = user_groups.get(id=active_group_id)
            data['group'] = group
            data['menu_list'] = self.__get_menu_list(data["user"], group)
        except Group.DoesNotExist:
            # Si el grupo no existe, limpiar la sesión
            if 'group_id' in self._request.session:
                del self._request.session['group_id']

    def _get_active_group_id(self, user_groups):
        """Determina el ID del grupo activo basado en varios factores."""
        # 1. Intenta obtener del POST (cambio de grupo via AJAX)
        if self._request.method == 'POST':
            posted_group_id = self._request.POST.get('group_id')
            if posted_group_id and user_groups.filter(id=posted_group_id).exists():
                self._request.session['group_id'] = int(posted_group_id)
                return int(posted_group_id)

        # 2. Intenta obtener del GET (cambio de grupo via URL)
        get_group_id = self._request.GET.get('gpid')
        if get_group_id and user_groups.filter(id=get_group_id).exists():
            self._request.session['group_id'] = int(get_group_id)
            return int(get_group_id)

        # 3. Intenta obtener de la sesión
        session_group_id = self._request.session.get('group_id')
        if session_group_id and user_groups.filter(id=session_group_id).exists():
            return session_group_id

        # 4. Si no hay grupo seleccionado, usa el primero
        first_group = user_groups.first()
        if first_group:
            self._request.session['group_id'] = first_group.id
            return first_group.id

        return None

    def __get_menu_list(self, user: User, group: Group):
        """
        Obtiene la lista de menús únicos para el grupo dado,
        junto con los módulos (submenús) asociados a cada menú.
        """
        try:
            # Obtenemos los permisos con toda la información necesaria
            permissions = GroupModulePermission.objects.get_permissions_for_group(group.id)
            
            # Diccionario temporal para agrupar por menú
            menu_dict = {}
            
            # Agrupamos los módulos por menú
            for perm in permissions:
                menu = perm.module.menu
                if menu.id not in menu_dict:
                    menu_dict[menu.id] = {
                        'menu': menu,
                        'group_module_permission_list': []
                    }
                menu_dict[menu.id]['group_module_permission_list'].append(perm)

            # Convertimos el diccionario a una lista ordenada por el orden del menú
            menu_list = list(menu_dict.values())
            menu_list.sort(key=lambda x: x['menu'].order)

            return menu_list

        except Exception as e:
            import traceback
            print(f"Error en __get_menu_list: {str(e)}")
            print(traceback.format_exc())
            return []

        # Construye la lista de menús con sus módulos
        menu_list = [
            self._get_data_menu_list(menu, group_module_permission_list)
            for menu in menu_unicos
        ]
        return menu_list

    def _get_data_menu_list(self, group_module_permission: GroupModulePermission, group_module_permission_list):
        """
        Para un menú dado, obtiene todos los módulos (submenús) que pertenecen a ese menú.
        """
        # Filtra los módulos que pertenecen al mismo menú
        group_module_permissions = group_module_permission_list.filter(
            module__menu_id=group_module_permission.module.menu_id
        )

        # Devuelve el menú y su lista de módulos
        return {
            'menu': group_module_permission.module.menu,
            'group_module_permission_list': group_module_permissions,
        }
