from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.html import format_html
from .models import User, Menu, Module, GroupModulePermission

@admin.register(User)
class CustomUserAdmin(UserAdmin):
    """
    Administración personalizada para el modelo User para VisionPulse
    """
    list_display = (
        'username', 'email', 'first_name', 'last_name', 'user_type', 
        'current_streak', 'total_sessions', 'is_premium', 
        'is_staff', 'is_active'
    )
    
    list_filter = (
        'user_type', 'work_environment', 'screen_size',
        'is_premium', 'is_active', 'is_staff', 'date_joined'
    )
    
    search_fields = ['username', 'email', 'first_name', 'last_name', 'company']
    
    ordering = ['-date_joined']
    
    # Configuración de fieldsets para VisionPulse
    fieldsets = UserAdmin.fieldsets + (
        ('Información Personal Extendida', {
            'fields': ('bio', 'birth_date', 'image')
        }),
        ('Información Profesional', {
            'fields': ('user_type', 'work_environment', 'company', 'job_title', 'screen_size')
        }),
        ('Configuraciones de Monitoreo', {
            'fields': ('monitoring_frequency', 'break_reminder_interval', 'auto_pause_on_fatigue', 
                      'exercise_difficulty', 'auto_suggest_exercises', 'preferred_work_time')
        }),
        ('Estadísticas de Salud Visual', {
            'fields': ('total_monitoring_time', 'total_sessions', 'current_streak', 'longest_streak',
                      'exercises_completed', 'breaks_taken', 'fatigue_episodes'),
            'classes': ('collapse',)
        }),
        ('Configuraciones de Sistema', {
            'fields': ('timezone_field', 'language', 'notifications_enabled', 'email_notifications',
                      'visual_fatigue_alerts', 'break_reminders', 'daily_reports'),
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