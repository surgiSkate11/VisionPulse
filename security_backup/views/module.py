from django.contrib import messages
from django.urls import reverse_lazy
from apps.security.components.mixin_crud import CreateViewMixin, DeleteViewMixin, ListViewMixin, PermissionMixin, UpdateViewMixin
from apps.security.forms.module import ModuleForm
from apps.security.models import Module
from django.views.generic import ListView, CreateView, UpdateView, DeleteView
from django.db.models import Q
from apps.security.components.sidebar_menu_mixin import SidebarMenuMixin


class ModuleListView(SidebarMenuMixin, PermissionMixin, ListViewMixin, ListView):
    template_name = 'security/modules/list.html'
    model = Module
    context_object_name = 'modules'
    permission_required = 'view_module'

    def get_queryset(self):
        q1 = self.request.GET.get('q')
        if q1 is not None:
            self.query.add(Q(name__icontains=q1), Q.OR)
            self.query.add(Q(menu__name__icontains=q1), Q.OR)
        return self.model.objects.filter(self.query).order_by('id')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['create_url'] = reverse_lazy('security:module_create')
        print(context['permissions'])
        return context


class ModuleCreateView(SidebarMenuMixin, PermissionMixin, CreateViewMixin, CreateView):
    model = Module
    template_name = 'security/modules/form.html'
    form_class = ModuleForm
    success_url = reverse_lazy('security:module_list')
    permission_required = 'add_module'

    def get_context_data(self, **kwargs):
        context = super().get_context_data()
        context['grabar'] = 'Grabar Módulo'
        context['back_url'] = self.success_url
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        module = self.object
        messages.success(self.request, f"Éxito al crear el módulo {module.name}.")
        return response


class ModuleUpdateView(SidebarMenuMixin, PermissionMixin, UpdateViewMixin, UpdateView):
    model = Module
    template_name = 'security/modules/form.html'
    form_class = ModuleForm
    success_url = reverse_lazy('security:module_list')
    permission_required = 'change_module'

    def get_context_data(self, **kwargs):
        context = super().get_context_data()
        context['grabar'] = 'Actualizar Módulo'
        context['back_url'] = self.success_url
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        module = self.object
        messages.success(self.request, f"Éxito al actualizar el módulo {module.name}.")
        return response


class ModuleDeleteView(SidebarMenuMixin, PermissionMixin, DeleteViewMixin, DeleteView):
    model = Module
    template_name = 'core/delete.html'
    success_url = reverse_lazy('security:module_list')
    permission_required = 'delete_module'

    def get_context_data(self, **kwargs):
        context = super().get_context_data()
        context['grabar'] = 'Eliminar Módulo'
        context['description'] = f"¿Desea eliminar el módulo: {self.object.name}?"
        context['back_url'] = self.success_url
        return context

    
    def form_valid(self, form):
        # Guardar info antes de eliminar
        module_name = self.object.name
        
        # Llamar al delete del padre
        response = super().form_valid(form)
        
        # Agregar mensaje
        messages.success(self.request, f"Éxito al eliminar lógicamente el módulo {module_name}.")
        
        return response