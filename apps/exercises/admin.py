# apps/exercises/admin.py
from django.contrib import admin
from django.utils.html import format_html
from django.db.models import Count, Avg, Q
from django.utils import timezone
from .models import Exercise, ExerciseStep, ExerciseSession

class ExerciseStepInline(admin.TabularInline):
    """
    Permite editar los pasos directamente desde la página del ejercicio.
    """
    model = ExerciseStep
    extra = 1
    ordering = ('step_order',)
    fields = ('step_order', 'instruction', 'video_clip', 'duration_seconds')

@admin.register(Exercise)
class ExerciseAdmin(admin.ModelAdmin):
    """
    Configuración del admin para el modelo Exercise.
    """
    list_display = (
        'title_with_icon', 
        'total_duration_display', 
        'total_steps', 
        'sessions_count',
        'completion_rate',
        'status_badge'
    )
    list_filter = ('is_active', 'created_at')
    search_fields = ('title', 'description')
    inlines = [ExerciseStepInline]
    readonly_fields = ('created_at', 'sessions_stats')
    
    fieldsets = (
        ('Información Básica', {
            'fields': ('title', 'description', 'icon_class', 'is_active')
        }),
        ('Estadísticas', {
            'fields': ('sessions_stats',),
            'classes': ('collapse',)
        })
    )
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(
            _sessions_count=Count('sessions'),
            _completed_sessions=Count('sessions', filter=Q(sessions__completed=True)),
            _avg_rating=Avg('sessions__rating')
        )
    
    def title_with_icon(self, obj):
        """Muestra el título con su ícono."""
        return format_html(
            '<i class="{}" style="margin-right: 8px; color: #4A90E2;"></i> <strong>{}</strong>',
            obj.icon_class,
            obj.title
        )
    title_with_icon.short_description = 'Ejercicio'
    title_with_icon.admin_order_field = 'title'
    
    def total_duration_display(self, obj):
        """Muestra la duración total con formato bonito."""
        minutes = obj.total_duration_minutes
        if minutes == 0:
            return format_html('<span style="color: #999;">Sin pasos</span>')
        return format_html(
            '<span style="background: #E3F2FD; padding: 3px 8px; border-radius: 3px; color: #1976D2;">'
            '<i class="far fa-clock"></i> {} min</span>',
            minutes
        )
    total_duration_display.short_description = 'Duración'
    
    def total_steps(self, obj):
        """Cuenta el número de pasos."""
        count = obj.steps.count()
        if count == 0:
            return format_html('<span style="color: #999;">0</span>')
        return format_html(
            '<span style="background: #F3E5F5; padding: 3px 8px; border-radius: 3px; color: #7B1FA2;">{}</span>',
            count
        )
    total_steps.short_description = 'Pasos'
    
    def sessions_count(self, obj):
        """Muestra el número total de sesiones."""
        count = obj._sessions_count
        return format_html(
            '<span style="background: #E8F5E9; padding: 3px 8px; border-radius: 3px; color: #388E3C;">{}</span>',
            count
        )
    sessions_count.short_description = 'Sesiones'
    sessions_count.admin_order_field = '_sessions_count'
    
    def completion_rate(self, obj):
        """Muestra la tasa de completitud."""
        total = obj._sessions_count
        if total == 0:
            return format_html('<span style="color: #999;">-</span>')
        completed = obj._completed_sessions
        rate = (completed / total) * 100
        
        if rate >= 80:
            color = '#4CAF50'
        elif rate >= 50:
            color = '#FF9800'
        else:
            color = '#F44336'
            
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}%</span> <span style="color: #999;">({}/{})</span>',
            color, int(rate), completed, total
        )
    completion_rate.short_description = 'Tasa Completitud'
    completion_rate.admin_order_field = '_completed_sessions'
    
    def status_badge(self, obj):
        """Muestra un badge del estado activo/inactivo."""
        if obj.is_active:
            return format_html(
                '<span style="background: #4CAF50; color: white; padding: 3px 10px; border-radius: 12px; font-size: 11px;">'
                '✓ ACTIVO</span>'
            )
        return format_html(
            '<span style="background: #9E9E9E; color: white; padding: 3px 10px; border-radius: 12px; font-size: 11px;">'
            '✕ INACTIVO</span>'
        )
    status_badge.short_description = 'Estado'
    status_badge.admin_order_field = 'is_active'
    
    def sessions_stats(self, obj):
        """Muestra estadísticas detalladas de las sesiones."""
        sessions = obj.sessions.all()
        total = sessions.count()
        
        if total == 0:
            return format_html('<p style="color: #999;">No hay sesiones registradas aún.</p>')
        
        completed = sessions.filter(completed=True).count()
        avg_rating = obj._avg_rating or 0
        completion_rate = round((completed/total*100), 1)
        stars = '⭐' * int(avg_rating)
        avg_rating_formatted = round(avg_rating, 1)
        
        html = '''
        <div style="background: #f5f5f5; padding: 15px; border-radius: 5px;">
            <h4 style="margin-top: 0;">Estadísticas de Sesiones</h4>
            <table style="width: 100%; border-collapse: collapse;">
                <tr>
                    <td style="padding: 5px;"><strong>Total de sesiones:</strong></td>
                    <td style="padding: 5px;">{}</td>
                </tr>
                <tr>
                    <td style="padding: 5px;"><strong>Completadas:</strong></td>
                    <td style="padding: 5px;">{} ({}%)</td>
                </tr>
                <tr>
                    <td style="padding: 5px;"><strong>En progreso:</strong></td>
                    <td style="padding: 5px;">{}</td>
                </tr>
                <tr>
                    <td style="padding: 5px;"><strong>Calificación promedio:</strong></td>
                    <td style="padding: 5px;">{} {}/5.0</td>
                </tr>
            </table>
        </div>
        '''
        return format_html(html, total, completed, completion_rate, total - completed, stars, avg_rating_formatted)
    sessions_stats.short_description = 'Estadísticas'

@admin.register(ExerciseSession)
class ExerciseSessionAdmin(admin.ModelAdmin):
    def session_title_local(self, obj):
        """Muestra el título de la sesión con la hora local de Ecuador (UTC-5)."""
        from django.utils.timezone import localtime
        import pytz
        status_icon = '✓' if obj.completed else '⏳'
        user = obj.user.username if obj.user else 'Sin usuario'
        exercise = obj.exercise.title if obj.exercise else 'Sin ejercicio'
        # Convertir a la zona horaria de Ecuador
        ecuador_tz = pytz.timezone('America/Guayaquil')
        local_dt = localtime(obj.created_at).astimezone(ecuador_tz)
        dt_str = local_dt.strftime('%Y-%m-%d %H:%M')
        return format_html(
            '<span style="font-weight:bold;">{}</span> {} - {} @ {}',
            status_icon, user, exercise, dt_str
        )
    session_title_local.short_description = 'Título (Hora Ecuador)'
    """
    Configuración del admin para ver el historial de sesiones.
    """
    list_display = (
        'id',
        'user_link',
        'exercise_link',
        'started_display',
        'completed_display',
        'duration_display',
        'completion_badge',
        'rating_display'
    )
    list_filter = (
        'completed',
        ('started_at', admin.DateFieldListFilter),
        'rating',
        'exercise'
    )
    search_fields = ('user__username', 'user__email', 'exercise__title')
    readonly_fields = (
        'user', 
        'exercise', 
        'started_at', 
        'completed_at', 
        'created_at',
        'session_details'
    )
    
    fieldsets = (
        ('Información de la Sesión', {
            'fields': ('user', 'exercise', 'started_at', 'completed_at', 'completed')
        }),
        ('Evaluación', {
            'fields': ('rating',)
        }),
        ('Detalles', {
            'fields': ('session_details',),
            'classes': ('collapse',)
        })
    )
    
    date_hierarchy = 'started_at'
    
    def has_add_permission(self, request):
        """No permitir crear sesiones manualmente."""
        return False
    
    def user_link(self, obj):
        """Muestra el usuario con un ícono."""
        return format_html(
            '<i class="fas fa-user" style="color: #2196F3; margin-right: 5px;"></i> {}',
            obj.user.username
        )
    user_link.short_description = 'Usuario'
    user_link.admin_order_field = 'user__username'
    
    def exercise_link(self, obj):
        """Muestra el ejercicio con su ícono."""
        if not obj.exercise:
            return format_html('<span style="color: #999;">Ejercicio Eliminado</span>')
        return format_html(
            '<i class="{}" style="margin-right: 5px; color: #4A90E2;"></i> {}',
            obj.exercise.icon_class,
            obj.exercise.title
        )
    exercise_link.short_description = 'Ejercicio'
    exercise_link.admin_order_field = 'exercise__title'
    
    def started_display(self, obj):
        """Muestra la fecha de inicio formateada."""
        return format_html(
            '<span style="white-space: nowrap;">{}</span>',
            obj.started_at.strftime('%d/%m/%Y %H:%M')
        )
    started_display.short_description = 'Inicio'
    started_display.admin_order_field = 'started_at'
    
    def completed_display(self, obj):
        """Muestra la fecha de completitud formateada."""
        if not obj.completed_at:
            return format_html('<span style="color: #999;">En progreso...</span>')
        return format_html(
            '<span style="white-space: nowrap; color: #4CAF50;">{}</span>',
            obj.completed_at.strftime('%d/%m/%Y %H:%M')
        )
    completed_display.short_description = 'Completado'
    completed_display.admin_order_field = 'completed_at'
    
    def duration_display(self, obj):
        """Muestra la duración real vs esperada."""
        actual_seconds = obj.duration_seconds()
        expected_seconds = obj.expected_duration_seconds()
        
        actual_min = round(actual_seconds / 60, 1)
        expected_min = round(expected_seconds / 60, 1)
        
        if expected_seconds == 0:
            return format_html('<span style="color: #999;">-</span>')
        
        percentage = obj.completion_percentage()
        
        if percentage >= 95:
            color = '#4CAF50'
            icon = '✓'
        elif percentage >= 50:
            color = '#FF9800'
            icon = '⧗'
        else:
            color = '#F44336'
            icon = '✕'
            
        return format_html(
            '<span style="color: {};">{} {}/{} min</span>',
            color, icon, actual_min, expected_min
        )
    duration_display.short_description = 'Duración (Real/Esperada)'
    
    def completion_badge(self, obj):
        """Muestra un badge de completitud con porcentaje."""
        if not obj.completed:
            return format_html(
                '<span style="background: #FFC107; color: white; padding: 4px 10px; border-radius: 12px; font-size: 11px;">'
                '⧗ EN PROGRESO</span>'
            )
        
        percentage = obj.completion_percentage()
        is_fully = obj.is_fully_completed()
        
        if is_fully:
            return format_html(
                '<span style="background: #4CAF50; color: white; padding: 4px 10px; border-radius: 12px; font-size: 11px;">'
                '✓ COMPLETADO {}%</span>',
                int(percentage)
            )
        else:
            return format_html(
                '<span style="background: #FF5722; color: white; padding: 4px 10px; border-radius: 12px; font-size: 11px;">'
                '✕ INCOMPLETO {}%</span>',
                int(percentage)
            )
    completion_badge.short_description = 'Estado'
    completion_badge.admin_order_field = 'completed'
    
    def rating_display(self, obj):
        """Muestra la calificación con estrellas."""
        if not obj.rating:
            return format_html('<span style="color: #999;">Sin calificar</span>')
        
        stars = '⭐' * obj.rating
        return format_html(
            '<span style="font-size: 14px;" title="{}/5">{}</span>',
            obj.rating, stars
        )
    rating_display.short_description = 'Calificación'
    rating_display.admin_order_field = 'rating'
    
    def session_details(self, obj):
        """Muestra detalles completos de la sesión."""
        actual_seconds = obj.duration_seconds()
        expected_seconds = obj.expected_duration_seconds()
        percentage = round(obj.completion_percentage(), 1)
        expected_min = round(expected_seconds/60, 1)
        actual_min = round(actual_seconds/60, 1)
        is_completed = "✓ Sí" if obj.is_fully_completed() else "✕ No"
        
        html = '''
        <div style="background: #f5f5f5; padding: 15px; border-radius: 5px;">
            <h4 style="margin-top: 0;">Detalles de la Sesión</h4>
            <table style="width: 100%; border-collapse: collapse;">
                <tr>
                    <td style="padding: 5px;"><strong>Duración esperada:</strong></td>
                    <td style="padding: 5px;">{} segundos ({} min)</td>
                </tr>
                <tr>
                    <td style="padding: 5px;"><strong>Duración real:</strong></td>
                    <td style="padding: 5px;">{} segundos ({} min)</td>
                </tr>
                <tr>
                    <td style="padding: 5px;"><strong>Porcentaje completado:</strong></td>
                    <td style="padding: 5px;">{}%</td>
                </tr>
                <tr>
                    <td style="padding: 5px;"><strong>¿Completado totalmente?:</strong></td>
                    <td style="padding: 5px;">{}</td>
                </tr>
            </table>
        </div>
        '''
        return format_html(html, expected_seconds, expected_min, actual_seconds, actual_min, percentage, is_completed)
    session_details.short_description = 'Detalles'

