from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from .models import MonitorSession, AlertEvent, AlertTypeConfig

@admin.register(MonitorSession)
class MonitorSessionAdmin(admin.ModelAdmin):
    """
    Admin interface options for MonitorSession model.
    """
    list_display = (
        'id',
        'user_link', # Link to the user admin page
        'start_time_local', # Display localized time
        'end_time_local',   # Display localized time
        'duration_display', # Display formatted duration
        'total_blinks',
        'total_yawns',  # 🔥 NUEVO
        'alerts_count',
        'avg_ear_display', # Display formatted EAR
        'focus_display',  # 🔥 NUEVO
    )
    list_filter = ('user', 'start_time')
    search_fields = ('user__email', 'user__username', 'id') # Search by user email/username or session ID
    readonly_fields = ('created_at', 'start_time', 'end_time', 'duration_seconds') # Fields not editable in admin
    list_per_page = 25
    ordering = ('-start_time',) # Show newest sessions first

    fieldsets = (
        (None, {
            'fields': ('user', 'camera')
        }),
        ('Timestamps & Duration', {
            'fields': ('start_time', 'end_time', 'duration_seconds'),
            'classes': ('collapse',) # Collapsible section
        }),
        ('Metrics', {
            'fields': ('total_blinks', 'total_yawns', 'avg_ear', 'avg_mar', 'focus_percent', 'alerts_count')
        }),
        ('Head Pose Metrics', {
            'fields': ('avg_head_yaw', 'avg_head_pitch', 'avg_head_roll', 'head_pose_variance'),
            'classes': ('collapse',)  # 🔥 NUEVO: Métricas de postura
        }),
        ('Quality Metrics', {
            'fields': ('avg_brightness', 'detection_rate'),
            'classes': ('collapse',)  # 🔥 NUEVO: Métricas de calidad
        }),
        ('Metadata', {
            'fields': ('metadata', 'final_metrics', 'created_at'),
            'classes': ('collapse',)
        }),
    )

    def user_link(self, obj):
        """Creates a link to the user admin page."""
        if obj.user:
            link = reverse("admin:security_user_change", args=[obj.user.id]) # Assumes 'security' app for User
            return format_html('<a href="{}">{}</a>', link, obj.user.email or obj.user.username)
        return "-"
    user_link.short_description = 'User'
    user_link.admin_order_field = 'user'

    def duration_display(self, obj):
        """Formats duration in minutes and seconds."""
        if obj.duration_seconds is not None:
            minutes = obj.duration_seconds // 60
            seconds = obj.duration_seconds % 60
            return f"{minutes}m {seconds}s"
        return "-"
    duration_display.short_description = 'Duration'
    duration_display.admin_order_field = 'duration_seconds'

    def start_time_local(self, obj):
        """Displays start_time in local timezone."""
        return obj.start_time.astimezone().strftime('%d/%m/%Y %H:%M:%S') if obj.start_time else '-'
    start_time_local.short_description = 'Start Time (Local)'
    start_time_local.admin_order_field = 'start_time'

    def end_time_local(self, obj):
        """Displays end_time in local timezone."""
        return obj.end_time.astimezone().strftime('%d/%m/%Y %H:%M:%S') if obj.end_time else '-'
    end_time_local.short_description = 'End Time (Local)'
    end_time_local.admin_order_field = 'end_time'

    def avg_ear_display(self, obj):
        """Formats average EAR."""
        return f"{obj.avg_ear:.3f}" if obj.avg_ear is not None else "-"
    avg_ear_display.short_description = 'Avg. EAR'
    avg_ear_display.admin_order_field = 'avg_ear'
    
    def focus_display(self, obj):
        """🔥 NUEVO: Formats focus percentage."""
        if obj.focus_percent is not None:
            color = (
                '#4CAF50' if obj.focus_percent >= 70
                else '#FF9800' if obj.focus_percent >= 50
                else '#F44336'
            )
            value_str = f"{obj.focus_percent:.1f}%"
            return format_html(
                '<span style="color: {};">{}</span>',
                color,
                value_str
            )
        return "-"
    focus_display.short_description = 'Enfoque'
    focus_display.admin_order_field = 'focus_percent'



@admin.register(AlertEvent)
class AlertEventAdmin(admin.ModelAdmin):
    """
    Admin interface options for AlertEvent model.
    """
    list_display = ('id', 'session_link', 'alert_type', 'triggered_at_local', 'resolved', 'resolved_at_local')
    list_filter = ('alert_type', 'resolved', 'session__user', 'triggered_at')
    search_fields = ('session__id', 'session__user__email', 'alert_type')
    readonly_fields = ('triggered_at', 'resolved_at')
    list_per_page = 30
    ordering = ('-triggered_at',)
    actions = ['mark_as_resolved'] # Action to resolve alerts

    fieldsets = (
         (None, {
            'fields': ('session', 'alert_type', 'message')
        }),
        ('Status & Timestamps', {
            'fields': ('triggered_at', 'resolved', 'resolved_at')
        }),
         ('Details', {
            'fields': ('metadata', 'voice_clip'),
            'classes': ('collapse',)
        }),
    )

    def session_link(self, obj):
        """Creates a link to the MonitorSession admin page."""
        link = reverse("admin:monitoring_monitorsession_change", args=[obj.session.id])
        return format_html('<a href="{}">Session {}</a>', link, obj.session.id)
    session_link.short_description = 'Session'
    session_link.admin_order_field = 'session'

    def triggered_at_local(self, obj):
        """Displays triggered_at in local timezone."""
        return obj.triggered_at.astimezone().strftime('%d/%m/%Y %H:%M:%S') if obj.triggered_at else '-'
    triggered_at_local.short_description = 'Triggered At (Local)'
    triggered_at_local.admin_order_field = 'triggered_at'

    def resolved_at_local(self, obj):
        """Displays resolved_at in local timezone."""
        return obj.resolved_at.astimezone().strftime('%d/%m/%Y %H:%M:%S') if obj.resolved_at else '-'
    resolved_at_local.short_description = 'Resolved At (Local)'
    resolved_at_local.admin_order_field = 'resolved_at'

    @admin.action(description='Mark selected alerts as resolved')
    def mark_as_resolved(self, request, queryset):
        """Admin action to mark alerts as resolved."""
        updated_count = 0
        for alert in queryset.filter(resolved=False):
            alert.mark_resolved() # Call the model method
            alert.save()
            updated_count += 1
        self.message_user(request, f'{updated_count} alerts marked as resolved.')


@admin.register(AlertTypeConfig)
class AlertTypeConfigAdmin(admin.ModelAdmin):
    """
    Admin interface for configuring default voice clips and descriptions per alert type.
    """
    list_display = ('alert_type_display', 'description_short', 'has_voice_clip', 'is_active', 'updated_at')
    list_filter = ('is_active', 'updated_at')
    search_fields = ('alert_type', 'description')
    readonly_fields = ('updated_at',)
    list_per_page = 20
    
    fieldsets = (
        (None, {
            'fields': ('alert_type', 'is_active')
        }),
        ('Content', {
            'fields': ('description', 'default_voice_clip')
        }),
        ('Metadata', {
            'fields': ('updated_at',),
            'classes': ('collapse',)
        }),
    )
    
    def alert_type_display(self, obj):
        """Display alert type with its human-readable label"""
        return format_html(
            '<strong>{}</strong><br><span style="color: #666; font-size: 11px;">{}</span>',
            obj.get_alert_type_display(),
            obj.alert_type
        )
    alert_type_display.short_description = 'Tipo de Alerta'
    alert_type_display.admin_order_field = 'alert_type'
    
    def description_short(self, obj):
        """Display shortened description"""
        if not obj.description:
            return format_html('<span style="color: #999;">Sin descripción</span>')
        desc = obj.description[:60] + '...' if len(obj.description) > 60 else obj.description
        return format_html('<span>{}</span>', desc)
    description_short.short_description = 'Descripción'
    
    def has_voice_clip(self, obj):
        """Display if alert type has a default voice clip"""
        if obj.default_voice_clip:
            return format_html(
                '<span style="color: #4CAF50;">✓ Sí</span>'
            )
        return format_html('<span style="color: #999;">✕ No</span>')
    has_voice_clip.short_description = 'Audio Default'
    has_voice_clip.admin_order_field = 'default_voice_clip'
