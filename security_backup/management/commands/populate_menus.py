from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from apps.security.models import Menu, Module, GroupModulePermission

class Command(BaseCommand):
    help = 'Puebla los menús, módulos y permisos básicos para Administrador y Estudiante.'

    def handle(self, *args, **options):
        # Menús principales
        menus = [
            {'name': 'Seguridad', 'icon': 'bi bi-shield-lock', 'order': 1},
            {'name': 'Perfil', 'icon': 'bi bi-person', 'order': 2},
            {'name': 'Cursos', 'icon': 'bi bi-book', 'order': 3},
            {'name': 'Configuración', 'icon': 'bi bi-gear', 'order': 4},
        ]
        menu_objs = {}
        for m in menus:
            obj, _ = Menu.objects.get_or_create(name=m['name'], defaults={'icon': m['icon'], 'order': m['order']})
            menu_objs[m['name']] = obj

        # Módulos por menú
        modules = [
            # Seguridad
            {'name': 'Usuarios', 'url': '/security/user_list/', 'menu': 'Seguridad', 'order': 1},
            {'name': 'Grupos', 'url': '/security/group_list/', 'menu': 'Seguridad', 'order': 2},
            # Faltantes:
            {'name': 'Crear usuario', 'url': '/security/user_create/', 'menu': 'Seguridad', 'order': 3},
            {'name': 'Editar usuario', 'url': '/security/user_update/', 'menu': 'Seguridad', 'order': 4},
            {'name': 'Eliminar usuario', 'url': '/security/user_delete/', 'menu': 'Seguridad', 'order': 5},
            {'name': 'Crear grupo', 'url': '/security/group_create/', 'menu': 'Seguridad', 'order': 6},
            {'name': 'Editar grupo', 'url': '/security/group_update/', 'menu': 'Seguridad', 'order': 7},
            {'name': 'Eliminar grupo', 'url': '/security/group_delete/', 'menu': 'Seguridad', 'order': 8},
            {'name': 'Permisos grupo', 'url': '/security/groupmodulepermission/', 'menu': 'Seguridad', 'order': 9},
            {'name': 'Menús', 'url': '/security/menu_list/', 'menu': 'Seguridad', 'order': 10},
            {'name': 'Crear menú', 'url': '/security/menu_create/', 'menu': 'Seguridad', 'order': 11},
            {'name': 'Editar menú', 'url': '/security/menu_update/', 'menu': 'Seguridad', 'order': 12},
            {'name': 'Eliminar menú', 'url': '/security/menu_delete/', 'menu': 'Seguridad', 'order': 13},
            {'name': 'Módulos', 'url': '/security/module_list/', 'menu': 'Seguridad', 'order': 14},
            {'name': 'Crear módulo', 'url': '/security/module_create/', 'menu': 'Seguridad', 'order': 15},
            {'name': 'Editar módulo', 'url': '/security/module_update/', 'menu': 'Seguridad', 'order': 16},
            {'name': 'Eliminar módulo', 'url': '/security/module_delete/', 'menu': 'Seguridad', 'order': 17},
            {'name': 'Configuración', 'url': '/security/settings/', 'menu': 'Configuración', 'order': 1},
        ]
        module_objs = {}
        for m in modules:
            # Buscar por URL primero para evitar duplicados
            obj = Module.objects.filter(url=m['url']).first()
            if not obj:
                obj, _ = Module.objects.get_or_create(
                    name=m['name'],
                    url=m['url'],
                    defaults={
                        'menu': menu_objs[m['menu']],
                        'order': m['order'],
                        'is_active': True
                    }
                )
            module_objs[m['name']] = obj

        # Grupos
        admin_group = Group.objects.get(name='Administrador')
        student_group = Group.objects.get(name='Estudiante')

        # Permisos básicos (puedes personalizar según tus modelos)
        all_permissions = Permission.objects.all()
        admin_perms = all_permissions
        student_perms = Permission.objects.filter(codename__in=['view_user'])

        # Asignar módulos y permisos a grupos
        for module in module_objs.values():
            # Admin: todos los módulos y permisos
            gmp_admin, _ = GroupModulePermission.objects.get_or_create(group=admin_group, module=module)
            gmp_admin.permissions.set(admin_perms)
            # Estudiante: solo módulos de perfil, cursos y configuración
            if module.name in ['Mi Perfil', 'Mis Cursos', 'Preferencias']:
                gmp_student, _ = GroupModulePermission.objects.get_or_create(group=student_group, module=module)
                gmp_student.permissions.set(student_perms)

        self.stdout.write(self.style.SUCCESS('Menús, módulos y permisos poblados correctamente.'))
