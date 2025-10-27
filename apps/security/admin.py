from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.html import format_html
from .models import User, Menu, Module, GroupModulePermission

# ============================================================
# CONFIGURACIÓN GLOBAL DEL ADMIN DE VISIONPULSE
# ============================================================
admin.site.site_header = '👁️ VisionPulse - Panel de Administración'
admin.site.site_title = 'VisionPulse Admin'
admin.site.index_title = 'Gestión del Sistema de Monitoreo Visual'


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    """
    Administración personalizada para el modelo User de VisionPulse.
    Organizada en secciones lógicas para facilitar la gestión de usuarios.
    """
    
    # ============================================================
    # CONFIGURACIÓN DE LISTA
    # ============================================================
    list_display = (
        'username', 
        'email', 
        'get_full_name_display',
        'user_type', 
        'current_streak', 
        'total_sessions',
        'is_active',
        'is_staff',
        'date_joined'
    )
    
    list_display_links = ('username', 'email')
    
    list_filter = (
        'is_active',
        'is_staff',
        'is_superuser',
        'user_type', 
        'work_environment', 
        'screen_size',
        'preferred_work_time',
        'date_joined',
        'last_login'
    )
    
    search_fields = [
        'username', 
        'email', 
        'first_name', 
        'last_name', 
        'company', 
        'job_title',
        'user_uuid'
    ]
    
    ordering = ['-date_joined']
    
    date_hierarchy = 'date_joined'
    
    list_per_page = 25
    
    # ============================================================
    # CONFIGURACIÓN DE FIELDSETS (FORMULARIO DE EDICIÓN)
    # ============================================================
    fieldsets = (
        # ──────────────────────────────────────────────────────
        # 🔐 AUTENTICACIÓN Y PERMISOS
        # ──────────────────────────────────────────────────────
        ('🔐 Credenciales de Acceso', {
            'fields': ('username', 'password'),
            'description': 'Información de autenticación del usuario'
        }),
        
        ('🛡️ Permisos y Roles', {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions'),
            'classes': ('collapse',),
            'description': 'Controla los permisos y roles del usuario en el sistema'
        }),
        
        # ──────────────────────────────────────────────────────
        # 👤 INFORMACIÓN PERSONAL
        # ──────────────────────────────────────────────────────
        ('👤 Información Personal', {
            'fields': ('first_name', 'last_name', 'email', 'phone', 'birth_date', 'image', 'bio'),
            'description': 'Datos personales del usuario'
        }),
        
        ('📍 Ubicación', {
            'fields': ('city', 'country', 'timezone', 'locale'),
            'classes': ('collapse',),
            'description': 'Información de ubicación y configuración regional'
        }),
        
        # ──────────────────────────────────────────────────────
        # 💼 INFORMACIÓN PROFESIONAL
        # ──────────────────────────────────────────────────────
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
        
        # ──────────────────────────────────────────────────────
        # 👁️ CONFIGURACIÓN DE MONITOREO VISUAL
        # ──────────────────────────────────────────────────────
        ('👁️ Métricas de Detección Ocular', {
            'fields': (
                'ear_threshold',
                'fatigue_threshold', 
                'microsleep_duration_seconds',
                'blink_window_frames',
            ),
            'classes': ('collapse',),
            'description': '⚙️ Configuración de detección de fatiga visual y microsueños mediante Eye Aspect Ratio (EAR)'
        }),
        
        ('😴 Tasa de Parpadeo', {
            'fields': (
                'low_blink_rate_threshold',
                'high_blink_rate_threshold',
            ),
            'classes': ('collapse',),
            'description': '⚙️ Umbrales para detectar parpadeo anormalmente bajo (sequedad) o alto (estrés/irritación)'
        }),
        
        ('🥱 Detección de Bostezos', {
            'fields': ('yawn_mar_threshold',),
            'classes': ('collapse',),
            'description': '⚙️ Sensibilidad para detectar bostezos mediante Mouth Aspect Ratio (MAR)'
        }),
        
        ('🧭 Pose de Cabeza y Postura', {
            'fields': (
                'distraction_angle_threshold',
                'postural_rigidity_duration_seconds',
            ),
            'classes': ('collapse',),
            'description': '⚙️ Detección de distracción (mirar fuera de la pantalla) y rigidez postural'
        }),
        
        ('💡 Ambiente de Trabajo', {
            'fields': ('low_light_threshold',),
            'classes': ('collapse',),
            'description': '⚙️ Umbral para detectar condiciones de iluminación inadecuadas'
        }),
        
        # ──────────────────────────────────────────────────────
        # ⚙️ CONFIGURACIÓN DEL SISTEMA DE MONITOREO
        # ──────────────────────────────────────────────────────
        ('⚙️ Sistema de Monitoreo', {
            'fields': (
                'camera_enabled',
                'face_detection_sensitivity',
                'sampling_interval_seconds',
                'monitoring_frequency',
                'break_reminder_interval',
            ),
            'classes': ('collapse',),
            'description': 'Configuración del sistema de captura y análisis de video'
        }),
        
        ('🎭 Overlay Facial (Rendimiento)', {
            'fields': (
                'face_overlay_enabled',
                'face_overlay_glow_intensity',
                'face_overlay_blur_sigma',
            ),
            'classes': ('collapse',),
            'description': '⚙️ Control del óvalo verde sobre el rostro. Desactivar o reducir en dispositivos de gama baja para mejor rendimiento'
        }),
        
        # ──────────────────────────────────────────────────────
        # 🎨 INTERFAZ Y NOTIFICACIONES
        # ──────────────────────────────────────────────────────
        ('🎨 Preferencias de Interfaz', {
            'fields': (
                'dark_mode',
                'notification_mode',
                'alert_volume',
                'notify_inactive_tab',
                'email_notifications',
            ),
            'classes': ('collapse',),
            'description': 'Personalización de la interfaz y sistema de notificaciones'
        }),
        
        # ──────────────────────────────────────────────────────
        # 🔒 PRIVACIDAD Y DATOS
        # ──────────────────────────────────────────────────────
        ('🔒 Privacidad y Consentimiento', {
            'fields': (
                'data_collection_consent',
                'anonymous_analytics',
            ),
            'classes': ('collapse',),
            'description': 'Configuración de privacidad y recolección de datos'
        }),
        
        # ──────────────────────────────────────────────────────
        # 📊 ESTADÍSTICAS DE SALUD VISUAL
        # ──────────────────────────────────────────────────────
        ('📊 Estadísticas de Uso', {
            'fields': (
                'total_monitoring_time',
                'total_sessions',
                'current_streak',
                'longest_streak',
            ),
            'classes': ('collapse',),
            'description': '📈 Métricas de uso y consistencia del usuario'
        }),
        
        ('🏋️ Ejercicios y Hábitos', {
            'fields': (
                'exercises_completed',
                'fatigue_episodes',
            ),
            'classes': ('collapse',),
            'description': '📈 Registro de actividades y eventos de salud visual'
        }),
        
        # ──────────────────────────────────────────────────────
        # 📅 METADATOS DEL SISTEMA
        # ──────────────────────────────────────────────────────
        ('📅 Información del Sistema', {
            'fields': (
                'user_uuid',
                'date_joined',
                'last_login',
                'updated_at',
            ),
            'classes': ('collapse',),
            'description': 'Información técnica y metadatos del registro'
        }),
    )
    
    # ============================================================
    # CONFIGURACIÓN PARA CREACIÓN DE USUARIOS
    # ============================================================
    add_fieldsets = (
        ('🔐 Información de Cuenta', {
            'classes': ('wide',),
            'fields': ('username', 'email', 'password1', 'password2'),
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
        'updated_at',
        'total_monitoring_time',
        'total_sessions',
        'current_streak',
        'longest_streak',
        'exercises_completed',
        'fatigue_episodes'
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
        """Reinicia las estadísticas de los usuarios seleccionados"""
        updated = queryset.update(
            total_monitoring_time=0,
            total_sessions=0,
            current_streak=0,
            longest_streak=0,
            exercises_completed=0,
            fatigue_episodes=0
        )
        self.message_user(request, f'Estadísticas reiniciadas para {updated} usuario(s).')

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
        count = obj.module_set.count()
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
    
    fieldsets = (
        ('📦 Información del Módulo', {
            'fields': ('name', 'url', 'menu', 'icon'),
            'description': 'Información básica del módulo'
        }),
        ('📝 Descripción', {
            'fields': ('description',),
        }),
        ('⚙️ Configuración', {
            'fields': ('is_active', 'order'),
            'description': 'Estado y orden de visualización del módulo'
        }),
    )
    
    actions = ['activate_modules', 'deactivate_modules']
    
    @admin.action(description='✅ Activar módulos seleccionados')
    def activate_modules(self, request, queryset):
        """Activa los módulos seleccionados"""
        updated = queryset.update(is_active=True)
        self.message_user(request, f'{updated} módulo(s) activado(s) correctamente.')
    
    @admin.action(description='🚫 Desactivar módulos seleccionados')
    def deactivate_modules(self, request, queryset):
        """Desactiva los módulos seleccionados"""
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated} módulo(s) desactivado(s) correctamente.')


@admin.register(GroupModulePermission)
class GroupModulePermissionAdmin(admin.ModelAdmin):
    """
    Administración de Permisos de Grupo por Módulo
    """
    list_display = ('group', 'module', 'get_permission_display')
    list_display_links = ('group', 'module')
    list_filter = ('group', 'module__menu', 'module')
    search_fields = ('group__name', 'module__name')
    ordering = ('group', 'module')
    list_per_page = 50
    
    fieldsets = (
        ('🔐 Asignación de Permisos', {
            'fields': ('group', 'module'),
            'description': 'Asigna permisos de acceso a módulos para grupos de usuarios'
        }),
    )
    
    @admin.display(description='Permiso')
    def get_permission_display(self, obj):
        """Muestra una descripción más clara del permiso"""
        return f'{obj.group.name} → {obj.module.name}'
    
    def has_add_permission(self, request):
        """Controla quien puede agregar permisos"""
        return request.user.is_superuser
    
    def has_delete_permission(self, request, obj=None):
        """Controla quien puede eliminar permisos"""
        return request.user.is_superuser