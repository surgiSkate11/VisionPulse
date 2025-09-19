# Vistas para el manejo de grupos, módulos y permisos de seguridad

from django.contrib import messages
from django.urls import reverse_lazy
from apps.security.components.mixin_crud import CreateViewMixin, DeleteViewMixin, ListViewMixin, PermissionMixin, UpdateViewMixin
from apps.security.forms.group_module_permisos import GroupModulePermissionForm
from apps.security.models import GroupModulePermission
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, TemplateView
from django.db.models import Q
from django.contrib.auth.models import Group, Permission
from apps.security.models import Module
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.views import View
import json
from apps.security.components.sidebar_menu_mixin import SidebarMenuMixin


class GroupModulePermissionListView(SidebarMenuMixin, PermissionMixin, ListViewMixin, ListView):
    template_name = 'security/grupos_modulos_permisos/list.html'
    model = GroupModulePermission
    context_object_name = 'GroupModulePermissions'
    permission_required = 'view_groupmodulepermission'

    def get_queryset(self):
        q1 = self.request.GET.get('q')
        if q1 is not None:
            self.query.add(Q(group__name__icontains=q1), Q.OR)
            self.query.add(Q(module__name__icontains=q1), Q.OR)
        # Ordenar por los más recientes primero
        return self.model.objects.filter(self.query).order_by('-id')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['create_url'] = reverse_lazy('security:group_module_permission_create')
        # --- INICIO: Datos para acordeones y permisos (igual que en CreateView) ---
        from django.contrib.auth.models import Group, Permission
        from apps.security.models import Module, GroupModulePermission
        all_groups = Group.objects.all()
        all_modules = Module.objects.all()
        existing_assignments = GroupModulePermission.objects.select_related('group', 'module').prefetch_related('permissions').all()
        groups_data = []
        for group in all_groups:
            assigned_modules = set(existing_assignments.filter(group=group).values_list('module_id', flat=True))
            available_modules = [
                {"id": m.id, "name": m.name, "icon": m.icon}
                for m in all_modules if m.id not in assigned_modules
            ]
            groups_data.append({
                "id": group.id,
                "name": group.name,
                "available_modules": available_modules
            })
        module_permissions = {}
        for module in all_modules:
            perms = module.permissions.all()
            module_permissions[module.id] = [
                {"id": p.id, "name": p.name, "codename": p.codename} for p in perms
            ]
        context.update({
            "groups_data": json.dumps(groups_data, ensure_ascii=False),
            "module_permissions": json.dumps(module_permissions, ensure_ascii=False),
        })
        # --- FIN: Datos para acordeones y permisos ---
        # Mostrar siempre los últimos 10 registros reales
        recent_db = self.model.objects.select_related('group', 'module').prefetch_related('permissions').order_by('-id')[:10]
        context['recent_assignments'] = [
            {
                'id': a.id,
                'group_id': a.group.id,
                'group_name': a.group.name,
                'module_id': a.module.id,
                'module_name': a.module.name,
                'module_icon': a.module.icon,
                'permissions': [{'id': p.id, 'name': p.name} for p in a.permissions.all()]
            }
            for a in recent_db
        ]
        return context

    def render_to_response(self, context, **response_kwargs):
        request = self.request
        # Si es AJAX y refresh=1, devuelve los datos de grupos y módulos en JSON
        if request.headers.get("x-requested-with") == "XMLHttpRequest" and request.GET.get('refresh') == '1':
            return JsonResponse({
                'groupsData': json.loads(context['groups_data']),
                'modulePermissions': json.loads(context['module_permissions'])
            })
        # Si es AJAX normal, devuelve solo el fragmento de la tabla
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            from django.template.loader import render_to_string
            from django.http import HttpResponse
            # Si viene de form.html (parámetro form=1), muestra solo la última asignación por grupo
            if request.GET.get('form') == '1':
                context = context.copy()
                session_assignments = request.session.get('recent_assignments', [])
                # Filtrar: solo la última asignación por grupo
                seen_groups = set()
                filtered = []
                for a in session_assignments:
                    if a['group_id'] not in seen_groups:
                        filtered.append(a)
                        seen_groups.add(a['group_id'])
                context['recent_assignments'] = filtered
            table_html = render_to_string('security/grupos_modulos_permisos/_table_fragment.html', context, request=request)
            return HttpResponse(table_html)
        else:
            return super().render_to_response(context, **response_kwargs)

    def get(self, request, *args, **kwargs):
        # Limpiar la sesión de asignaciones recientes al entrar a la lista completa
        if 'recent_assignments' in request.session:
            del request.session['recent_assignments']
            request.session.modified = True
        return super().get(request, *args, **kwargs)


class GroupModulePermissionCreateView(SidebarMenuMixin, PermissionMixin, CreateViewMixin, CreateView):
    model = GroupModulePermission
    template_name = 'security/grupos_modulos_permisos/form.html'
    form_class = GroupModulePermissionForm
    success_url = reverse_lazy('security:group_module_permission_list')
    permission_required = 'add_groupmodulepermission'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['grabar'] = 'Grabar Grupo Módulo Permiso'
        context['back_url'] = self.success_url
        # Limpiar asignaciones anteriores de la sesión al acceder al formulario
        if 'recent_assignments' in self.request.session:
            del self.request.session['recent_assignments']
            self.request.session.modified = True
        # Obtener todos los datos necesarios para la página dinámica
        all_groups = Group.objects.all()
        all_modules = Module.objects.all()
        existing_assignments = GroupModulePermission.objects.select_related('group', 'module').prefetch_related('permissions').all()
        # Datos para los acordeones dinámicos
        groups_data = []
        for group in all_groups:
            assigned_modules = set(existing_assignments.filter(group=group).values_list('module_id', flat=True))
            available_modules = [
                {"id": m.id, "name": m.name, "icon": m.icon} 
                for m in all_modules if m.id not in assigned_modules
            ]
            groups_data.append({
                "id": group.id,
                "name": group.name,
                "available_modules": available_modules
            })
        # Relación módulo → permisos
        module_permissions = {}
        for module in all_modules:
            perms = module.permissions.all()
            module_permissions[module.id] = [
                {"id": p.id, "name": p.name, "codename": p.codename} for p in perms
            ]
        # Asignaciones recientes de la sesión (solo las que el usuario ha creado en esta sesión)
        session_assignments = self.request.session.get('recent_assignments', [])
        assignments_data = session_assignments[:5]  # Mostrar solo las primeras 5
        context.update({
            "groups_data": json.dumps(groups_data),
            "module_permissions": json.dumps(module_permissions),
            "assignments_data": json.dumps(assignments_data),
            "all_groups": all_groups,
            "all_modules": all_modules,
            "recent_assignments": assignments_data,  # <-- Solo las primeras 5 para el fragmento
            "show_actions": False  # No mostrar acciones en el formulario
        })
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        grupo_modulo_permiso = self.object
        messages.success(self.request, f"Éxito al crear el grupo módulo permiso {grupo_modulo_permiso.id}.")
        return response

    def get(self, request, *args, **kwargs):
        # Limpiar asignaciones recientes de la sesión al entrar al formulario
        if 'recent_assignments' in request.session:
            del request.session['recent_assignments']
            request.session.modified = True
        return super().get(request, *args, **kwargs)


class GroupModulePermissionUpdateView(SidebarMenuMixin, PermissionMixin, UpdateViewMixin, UpdateView):
    model = GroupModulePermission
    template_name = 'security/grupos_modulos_permisos/form_update.html'
    form_class = GroupModulePermissionForm
    success_url = reverse_lazy('security:group_module_permission_list')
    permission_required = 'change_groupmodulepermission'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['grabar'] = 'Actualizar Grupo Módulo Permiso'
        context['back_url'] = self.success_url
        # No es necesario pasar más datos, el template usa self.object
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        group_module_permission = self.object
        messages.success(self.request, f"Éxito al actualizar el grupo módulo permiso {group_module_permission.module.name}.")
        return response


class GroupModulePermissionDeleteView(SidebarMenuMixin, PermissionMixin, DeleteViewMixin, DeleteView):
    model = GroupModulePermission
    template_name = 'core/delete.html'
    success_url = reverse_lazy('security:group_module_permission_list')
    permission_required = 'delete_groupmodulepermission'

    def get_context_data(self, **kwargs):
        context = super().get_context_data()
        context['grabar'] = 'Eliminar Grupo Módulo Permiso'
        context['description'] = f"¿Desea eliminar el grupo módulo permiso: {self.object.id}?"
        context['back_url'] = self.success_url
        return context

    
    def form_valid(self, form):
        # Guardar info antes de eliminar
        group_module_permission = self.object
        response = super().form_valid(form)
        messages.success(self.request, f"Éxito al eliminar el grupo módulo permiso {group_module_permission.module.name}.")

        return response


@method_decorator(csrf_exempt, name='dispatch')
class GroupModulePermissionAjaxView(PermissionMixin, View):
    permission_required = 'add_groupmodulepermission'
    
    def post(self, request, *args, **kwargs):
        try:
            data = json.loads(request.body)
            group_id = data.get('group_id')
            module_id = data.get('module_id')
            permission_ids = data.get('permission_ids', [])
            
            # Validar que los datos estén completos
            if not group_id or not module_id or not permission_ids:
                return JsonResponse({
                    'success': False, 
                    'message': 'Datos incompletos: grupo, módulo y al menos un permiso son requeridos.'
                })
            
            # Obtener objetos
            try:
                group = Group.objects.get(id=group_id)
                module = Module.objects.get(id=module_id)
                permissions = Permission.objects.filter(id__in=permission_ids)
            except (Group.DoesNotExist, Module.DoesNotExist):
                return JsonResponse({
                    'success': False, 
                    'message': 'Grupo o módulo no encontrado.'
                })
            
            # Verificar si ya existe una asignación para este grupo y módulo
            existing = GroupModulePermission.objects.filter(group=group, module=module).first()
            if existing:
                return JsonResponse({
                    'success': False, 
                    'message': f'Ya existe una asignación para el grupo "{group.name}" y módulo "{module.name}".'
                })
              # Crear nueva asignación
            assignment = GroupModulePermission.objects.create(
                group=group,
                module=module
            )
            assignment.permissions.set(permissions)
            
            # Datos de respuesta
            assignment_data = {
                'id': assignment.id,
                'group_id': group.id,
                'group_name': group.name,
                'module_id': module.id,
                'module_name': module.name,
                'module_icon': module.icon,
                'permissions': [{'id': p.id, 'name': p.name} for p in permissions]
            }
            
            # Guardar en la sesión para mostrar en la tabla de asignaciones recientes
            if 'recent_assignments' not in request.session:
                request.session['recent_assignments'] = []
            # Insertar al inicio para que los más recientes aparezcan primero
            request.session['recent_assignments'].insert(0, assignment_data)
            request.session.modified = True
            # DEBUG: Imprimir en consola del servidor el contenido de la sesión
            print('DEBUG recent_assignments:', request.session['recent_assignments'])
            response_data = {
                'success': True,
                'message': f'Asignación creada exitosamente para {group.name} - {module.name}.',
                'assignment': assignment_data
            }
            
            return JsonResponse(response_data)
            
        except json.JSONDecodeError:
            return JsonResponse({
                'success': False, 
                'message': 'Error en el formato de datos enviados.'
            })
        except Exception as e:            return JsonResponse({
                'success': False, 
                'message': f'Error interno: {str(e)}'
            })

    def delete(self, request, pk=None):
        try:
            if not pk:
                return JsonResponse({
                    'success': False, 
                    'message': 'ID de asignación requerido.'
                })
            
            assignment = GroupModulePermission.objects.get(id=pk)
            assignment_info = f"{assignment.group.name} - {assignment.module.name}"
            assignment.delete()
            
            # También remover de la sesión si existe
            if 'recent_assignments' in request.session:
                request.session['recent_assignments'] = [
                    a for a in request.session['recent_assignments'] 
                    if a['id'] != pk
                ]
                request.session.modified = True
            
            return JsonResponse({
                'success': True,
                'message': f'Asignación "{assignment_info}" eliminada exitosamente.'
            })
            
        except GroupModulePermission.DoesNotExist:
            return JsonResponse({
                'success': False, 
                'message': 'Asignación no encontrada.'
            })
        except Exception as e:
            return JsonResponse({
                'success': False, 
                'message': f'Error interno: {str(e)}'
            })