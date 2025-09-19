from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.html import format_html
from .models import User, Menu, Module, GroupModulePermission

@admin.register(User)
class CustomUserAdmin(UserAdmin):
    """
    Administración personalizada para el modelo User combinando funcionalidades 
    del sistema original con características de Studer
    """
    list_display = (
        'username', 'email', 'first_name', 'last_name', 'user_type', 
        'current_level', 'total_xp', 'current_streak', 'is_premium', 
        'is_staff', 'is_active'
    )
    
    list_filter = (
        'user_type', 'study_level', 'learning_style',
        'is_premium', 'is_active', 'is_staff', 'date_joined'
    )
    
    search_fields = ['username', 'email', 'first_name', 'last_name', 'institution']
    
    ordering = ['-date_joined']
    
    # Configuración de fieldsets para incluir campos de Studer
    fieldsets = UserAdmin.fieldsets + (
        ('Información Personal Extendida', {
            'fields': ('bio', 'birth_date', 'image')
        }),
        ('Información Académica', {
            'fields': ('user_type', 'study_level', 'institution', 'major')
        }),
        ('Configuraciones de Aprendizaje', {
            'fields': ('learning_style', 'preferred_study_time')
        }),
        ('Gamificación', {
            'fields': ('total_xp', 'current_level', 'current_streak', 'longest_streak'),
            'classes': ('collapse',)
        }),
        ('Estadísticas de Estudio', {
            'fields': ('total_study_time', 'tasks_completed', 'notes_created'),
            'classes': ('collapse',)
        }),
        ('Configuraciones de Sistema', {
            'fields': ('timezone_field', 'language', 'notifications_enabled', 'email_notifications'),
            'classes': ('collapse',)
        }),
        ('Suscripción', {
            'fields': ('is_premium', 'premium_until'),
            'classes': ('collapse',)
        }),
        ('Metadatos', {
            'fields': ('uuid', 'last_activity', 'is_verified'),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = ['uuid', 'date_joined', 'last_activity']

@admin.register(Menu)
class MenuAdmin(admin.ModelAdmin):
    list_display = ('name', 'icon', 'order')
    search_fields = ('name',)
    ordering = ('order', 'name')

@admin.register(Module)
class ModuleAdmin(admin.ModelAdmin):
    list_display = ('name', 'url', 'menu', 'is_active', 'order')
    list_filter = ('menu', 'is_active')
    search_fields = ('name', 'url', 'description')
    ordering = ('menu', 'order', 'name')

@admin.register(GroupModulePermission)
class GroupModulePermissionAdmin(admin.ModelAdmin):
    list_display = ('group', 'module')
    list_filter = ('group', 'module')
    filter_horizontal = ('permissions',)


# from django import forms
# from .models import GroupModulePermission

# class GroupModulePermissionAdminForm(forms.ModelForm):
#     class Meta:
#         model = GroupModulePermission
#         fields = '__all__'

#     def __init__(self, *args, **kwargs):
#         super().__init__(*args, **kwargs)
#         # Si ya hay un módulo seleccionado (en edición o POST)
#         if 'module' in self.data:
#             try:
#                 module_id = int(self.data.get('module'))
#                 module = self.fields['module'].queryset.get(pk=module_id)
#                 self.fields['permissions'].queryset = module.permissions.all()
#             except Exception:
#                 self.fields['permissions'].queryset = self.fields['permissions'].queryset.none()
#         elif self.instance.pk:
#             self.fields['permissions'].queryset = self.instance.module.permissions.all()
#         else:
#             self.fields['permissions'].queryset = self.fields['permissions'].queryset.none()

# @admin.register(GroupModulePermission)
# class GroupModulePermissionAdmin(admin.ModelAdmin):
#     form = GroupModulePermissionAdminForm
#     list_display = ('group', 'module')
#     list_filter = ('group', 'module')
#     filter_horizontal = ('permissions',)