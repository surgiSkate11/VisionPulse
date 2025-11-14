from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.html import format_html
from .models import User, Menu, Module, GroupModulePermission

# Importamos el modelo de configuración para usarlo en la acción
try:
    from monitoring.models import UserMonitoringConfig
except ImportError:
    # Manejo opcional por si la app monitoring no está instalada
    UserMonitoringConfig = None

# ============================================================
# CONFIGURACIÓN GLOBAL DEL ADMIN DE VISIONPULSE
# ============================================================
admin.site.site_header = '👁️ VisionPulse - Panel de Administración'
admin.site.site_title = 'VisionPulse Admin'
admin.site.index_title = 'Gestión del Sistema de Monitoreo Visual'


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = (
        'username',
        'email',
        'get_full_name_display',
        'notification_sound',
        'is_staff',
        'is_active',
        'last_login'
    )
    list_filter = (
        'is_active',
        'is_staff',
        'is_superuser',
        'groups',
        'user_type' # Asumiendo que user_type es un campo filtrable
    )

    # --- FIELDSETS CORREGIDOS ---
    # Eliminados todos los campos que no pertenecen al modelo User
    # (p.ej. total_sessions, dark_mode, face_overlay_enabled, etc.)
    fieldsets = (
        ('🔐 Credenciales de Acceso', {
            'fields': ('username', 'password'),
            'description': 'Información de autenticación del usuario'
        }),
        ('🛡️ Permisos y Roles', {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions'),
            'classes': ('collapse',),
            'description': 'Controla los permisos y roles del usuario en el sistema'
        }),
        ('👤 Información Personal', {
            'fields': ('first_name', 'last_name', 'email', 'phone', 'birth_date', 'image', 'bio'),
            'description': 'Datos personales del usuario'
        }),
        ('📍 Ubicación', {
            # Corregido: Eliminados 'timezone' y 'locale' que no están en el modelo User
            'fields': ('city', 'country'),
            'classes': ('collapse',),
            'description': 'Información de ubicación y configuración regional'
        }),
        ('💼 Perfil Profesional', {
            'fields': (
                'user_type',
                'work_environment', 
                'company', 
                'job_title', 
                'screen_size',
                'preferred_work_time'
            ),
            'classes': ('collapse',),
            'description': 'Información laboral y configuración del entorno de trabajo'
        }),
        ('� Configuración de Notificaciones', {
            'fields': (
                'notification_sound',
                'notification_sound_enabled',
                'email_notifications'
            ),
            'classes': ('collapse',),
            'description': 'Preferencias de notificaciones del usuario'
        }),
        ('📊 Estadísticas de Salud Visual', {
            'fields': (
                'total_monitoring_time',
                'total_sessions',
                'current_streak',
                'longest_streak',
                'exercises_completed',
                'fatigue_episodes'
            ),
            'classes': ('collapse',),
            'description': 'Estadísticas de uso y salud visual'
        }),
        ('📅 Información del Sistema', {
            'fields': (
                'user_uuid',
                'date_joined',
                'last_login',
                'updated_at',
            ),
            'classes': ('collapse',),
            'description': 'Metadatos y fechas importantes del usuario'
        }),
    )
    
    # ============================================================
    # CONFIGURACIÓN PARA CREACIÓN DE USUARIOS
    # ============================================================
    add_fieldsets = (
        ('🔐 Información de Cuenta', {
            'classes': ('wide',),
            'fields': ('username', 'email', 'password', 'password2'), # Asumiendo que usas 'password' y 'password2' del form
        }),
        ('👤 Información Personal', {
            'classes': ('wide',),
            'fields': ('first_name', 'last_name', 'user_type'),
        }),
    )
    
    # ============================================================
    # CAMPOS DE SOLO LECTURA
    # ============================================================
    readonly_fields = [
        'user_uuid', 
        'date_joined', 
        'last_login',
        'updated_at'
    ]
    
    # ============================================================
    # MÉTODOS PERSONALIZADOS PARA DISPLAY
    # ============================================================
    @admin.display(description='Nombre Completo', ordering='first_name')
    def get_full_name_display(self, obj):
        """Muestra el nombre completo del usuario"""
        full_name = obj.get_full_name()
        return full_name if full_name else '(Sin nombre)'
    
    # ============================================================
    # ACCIONES PERSONALIZADAS
    # ============================================================
    actions = ['activate_users', 'deactivate_users', 'reset_statistics']
    
    @admin.action(description='✅ Activar usuarios seleccionados')
    def activate_users(self, request, queryset):
        """Activa los usuarios seleccionados"""
        updated = queryset.update(is_active=True)
        self.message_user(request, f'{updated} usuario(s) activado(s) correctamente.')
    
    @admin.action(description='🚫 Desactivar usuarios seleccionados')
    def deactivate_users(self, request, queryset):
        """Desactiva los usuarios seleccionados"""
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated} usuario(s) desactivado(s) correctamente.')
    
    @admin.action(description='🔄 Reiniciar estadísticas de usuarios')
    def reset_statistics(self, request, queryset):
        """
        Reinicia las estadísticas que están EN EL MODELO USER.
        """
        updated_count = queryset.update(
            total_monitoring_time=0,
            total_sessions=0,
            current_streak=0,
            longest_streak=0,
            exercises_completed=0,
            fatigue_episodes=0,
            last_streak_update=None
        )
        self.message_user(request, f'Estadísticas reiniciadas para {updated_count} usuario(s).')

@admin.register(Menu)
class MenuAdmin(admin.ModelAdmin):
    """
    Administración de Menús del sistema
    """
    list_display = ('name', 'icon', 'order', 'get_modules_count')
    list_display_links = ('name',)
    search_fields = ('name',)
    ordering = ('order', 'name')
    list_per_page = 50
    
    fieldsets = (
        ('📋 Información del Menú', {
            'fields': ('name', 'icon', 'order'),
            'description': 'Configuración básica del elemento de menú'
        }),
    )
    
    @admin.display(description='Módulos')
    def get_modules_count(self, obj):
        """Cuenta los módulos asociados a este menú"""
        count = obj.modules.count()
        return f'{count} módulo(s)'


@admin.register(Module)
class ModuleAdmin(admin.ModelAdmin):
    """
    Administración de Módulos del sistema
    """
    list_display = ('name', 'url', 'menu', 'is_active', 'order', 'icon')
    list_display_links = ('name',)
    list_filter = ('menu', 'is_active')
    search_fields = ('name', 'url', 'description')
    ordering = ('menu', 'order', 'name')
    list_per_page = 50
    list_editable = ('is_active', 'order')