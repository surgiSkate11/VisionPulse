from django.contrib import messages
from django.urls import reverse_lazy
from apps.security.components.mixin_crud import CreateViewMixin, DeleteViewMixin, ListViewMixin, PermissionMixin, UpdateViewMixin
from apps.security.forms.user import UserForm
from apps.security.models import User
from django.views.generic import ListView, CreateView, UpdateView, DeleteView
from django.db.models import Q
from apps.security.components.sidebar_menu_mixin import SidebarMenuMixin

class UserListView(SidebarMenuMixin, PermissionMixin, ListViewMixin, ListView):
    template_name = 'security/usuarios/list.html'
    model = User
    context_object_name = 'users'
    permission_required = 'view_user'

    def get_queryset(self):
        q1 = self.request.GET.get('q')
        query = Q()
        if q1:
            query |= Q(username__icontains=q1)
            query |= Q(email__icontains=q1)
            query |= Q(first_name__icontains=q1)
            query |= Q(last_name__icontains=q1)
            query |= Q(dni__icontains=q1)
        return self.model.objects.filter(query).order_by('id')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['create_url'] = reverse_lazy('security:user_create')
        context['title'] = 'Usuarios'
        context['title1'] = 'Usuarios'
        return context

class UserCreateView(SidebarMenuMixin, PermissionMixin, CreateViewMixin, CreateView):
    model = User
    template_name = 'security/usuarios/form.html'
    form_class = UserForm
    success_url = reverse_lazy('security:user_list')
    permission_required = 'add_user'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['grabar'] = 'Crear Usuario'
        context['back_url'] = self.success_url
        context['title'] = 'Nuevo Usuario'
        context['title1'] = 'Nuevo Usuario'
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        user = self.object
        messages.success(self.request, f"Éxito al crear el usuario {user.username}.")
        return response

class UserUpdateView(SidebarMenuMixin, PermissionMixin, UpdateViewMixin, UpdateView):
    model = User
    template_name = 'security/usuarios/form.html'
    form_class = UserForm
    success_url = reverse_lazy('security:user_list')
    permission_required = 'change_user'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['grabar'] = 'Actualizar Usuario'
        context['back_url'] = self.success_url
        context['title'] = 'Editar Usuario'
        context['title1'] = 'Editar Usuario'
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        user = self.object
        messages.success(self.request, f"Éxito al actualizar el usuario {user.username}.")
        return response

class UserDeleteView(SidebarMenuMixin, PermissionMixin, DeleteViewMixin, DeleteView):
    model = User
    template_name = 'core/delete.html'
    success_url = reverse_lazy('security:user_list')
    permission_required = 'delete_user'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['grabar'] = 'Eliminar Usuario'
        context['description'] = f"¿Desea eliminar el usuario: {self.object.username}?"
        context['back_url'] = self.success_url
        return context

    def form_valid(self, form):
        user_name = self.object.username
        response = super().form_valid(form)
        messages.success(self.request, f"Éxito al eliminar lógicamente el usuario {user_name}.")
        return response