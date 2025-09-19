from datetime import datetime
from django.contrib.auth.models import Group
from django.http import HttpRequest

from apps.security.models import GroupModulePermission, User

class MenuModule:
    def __init__(self, request: HttpRequest):
        # Guarda el request y la ruta actual
        self._request = request
        self._path = self._request.path

    def fill(self, data):
        """
        Añade información relevante al diccionario 'data' y a la sesión:
        - Usuario autenticado
        - Fecha y hora actual
        - Lista de grupos del usuario
        - Grupo seleccionado y menús asociados
        """
        data['user'] = self._request.user
        data['date_time'] = datetime.now()
        data['date_date'] = datetime.now().date()

        if self._request.user.is_authenticated:
            # Siempre añade group_list, sin importar el método
            data['group_list'] = self._request.user.groups.all().order_by('id')

            # Si se recibe un cambio de grupo por POST (AJAX), actualizar la sesión
            if self._request.method == 'POST' and self._request.POST.get('group_id'):
                group_id = self._request.POST.get('group_id')
                if data['group_list'].filter(id=group_id).exists():
                    self._request.session['group_id'] = int(group_id)

            # Si no hay grupo seleccionado en la sesión, selecciona el primero
            if 'group_id' not in self._request.session:
                if data['group_list'].exists():
                    self._request.session['group_id'] = data['group_list'].first().id

            # Si hay grupo seleccionado en la sesión
            if self._request.session.get('group_id'):
                # Permite cambiar de grupo si se recibe el parámetro 'gpid'
                group_id = self._request.GET.get('gpid', None)
                if group_id is not None:
                    self._request.session['group_id'] = data['group_list'].get(id=group_id).id

                # Obtiene el grupo actual y la lista de menús asociados
                group = Group.objects.get(id=self._request.session['group_id'])
                data['group'] = group
                data['menu_list'] = self.__get_menu_list(data["user"], group)

    def __get_menu_list(self, user: User, group: Group):
        """
        Obtiene la lista de menús únicos para el grupo dado,
        junto con los módulos (submenús) asociados a cada menú.
        """
        # Lista de permisos activos de módulos para el grupo
        group_module_permission_list = GroupModulePermission.objects.get_group_module_permission_active_list(group.id).order_by('module__order')

        # Obtiene menús únicos (evita repetidos)
        menu_unicos = group_module_permission_list.order_by('module__menu_id').distinct('module__menu_id')

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
