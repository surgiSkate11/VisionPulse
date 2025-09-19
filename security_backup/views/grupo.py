from django.contrib import messages
from django.urls import reverse_lazy
from apps.security.components.mixin_crud import (
    CreateViewMixin, DeleteViewMixin, ListViewMixin, PermissionMixin, UpdateViewMixin
)
from apps.security.forms.group import GroupForm
from django.contrib.auth.models import Group
from django.views.generic import ListView, CreateView, UpdateView, DeleteView
from django.db.models import Q
from apps.security.components.sidebar_menu_mixin import SidebarMenuMixin

class GroupListView(SidebarMenuMixin, PermissionMixin, ListViewMixin, ListView):
    template_name = 'security/grupos/list.html'
    model = Group
    context_object_name = 'groups'
    permission_required = 'auth.view_group'

    def get_queryset(self):
        q1 = self.request.GET.get('q')
        query = Q()
        if q1:
            query |= Q(name__icontains=q1)
        return self.model.objects.filter(query).order_by('id')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['create_url'] = reverse_lazy('security:group_create')
        context['title'] = 'Grupos'
        context['title1'] = 'Grupos'
        return context

class GroupCreateView(SidebarMenuMixin, PermissionMixin, CreateViewMixin, CreateView):
    model = Group
    template_name = 'security/grupos/form.html'
    form_class = GroupForm
    success_url = reverse_lazy('security:group_list')
    permission_required = 'auth.add_group'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['grabar'] = 'Crear Grupo'
        context['back_url'] = self.success_url
        context['title'] = 'Nuevo Grupo'
        context['title1'] = 'Nuevo Grupo'
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        group = self.object
        messages.success(self.request, f"Éxito al crear el grupo {group.name}.")
        return response

class GroupUpdateView(SidebarMenuMixin, PermissionMixin, UpdateViewMixin, UpdateView):
    model = Group
    template_name = 'security/grupos/form.html'
    form_class = GroupForm
    success_url = reverse_lazy('security:group_list')
    permission_required = 'auth.change_group'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['grabar'] = 'Actualizar Grupo'
        context['back_url'] = self.success_url
        context['title'] = 'Editar Grupo'
        context['title1'] = 'Editar Grupo'
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        group = self.object
        messages.success(self.request, f"Éxito al actualizar el grupo {group.name}.")
        return response

class GroupDeleteView(SidebarMenuMixin, PermissionMixin, DeleteViewMixin, DeleteView):
    model = Group
    template_name = 'core/delete.html'
    success_url = reverse_lazy('security:group_list')
    permission_required = 'auth.delete_group'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['grabar'] = 'Eliminar Grupo'
        context['description'] = f"¿Desea eliminar el grupo: {self.object.name}?"
        context['back_url'] = self.success_url
        return context

    def form_valid(self, form):
        group_name = self.object.name
        response = super().form_valid(form)
        messages.success(self.request, f"Éxito al eliminar el grupo {group_name}.")
        return response