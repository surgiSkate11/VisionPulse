from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, Menu, Module, GroupModulePermission

@admin.register(User)
class CustomUserAdmin(UserAdmin):
    """
    Administración personalizada para el modelo User para VisionPulse
    """
    list_display = (
        'username', 'email', 'first_name', 'last_name', 'user_type', 
        'current_streak', 'total_sessions',
        'is_staff', 'is_active'
    )
    
    list_filter = (
        'user_type', 'work_environment', 'screen_size',
        'is_active', 'is_staff', 'date_joined'
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
            'fields': ('monitoring_frequency', 'break_reminder_interval', 'preferred_work_time')
        }),
        ('Estadísticas de Salud Visual', {
            'fields': ('total_monitoring_time', 'total_sessions', 'current_streak', 'longest_streak',
                      'exercises_completed', 'breaks_taken', 'fatigue_episodes'),
            'classes': ('collapse',)
        }),
        ('Configuraciones de Sistema', {
            'fields': (
                'ear_threshold', 'blink_window_frames', 'blink_rate_threshold',
                'dark_mode', 'notification_mode', 'alert_volume', 'data_collection_consent',
                'anonymous_analytics', 'camera_enabled', 'face_detection_sensitivity',
                'fatigue_threshold', 'sampling_interval_seconds', 'notify_inactive_tab',
                'locale', 'timezone',
            ),
            'classes': ('collapse',)
        }),
        ('Metadatos', {
            'fields': ('user_uuid', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = ['user_uuid', 'date_joined', 'updated_at']

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