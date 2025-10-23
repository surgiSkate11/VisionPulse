from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from .models import MonitorSession, BlinkEvent, AlertEvent

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
        'alerts_count',
        'avg_ear_display', # Display formatted EAR
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
            'fields': ('total_blinks', 'avg_ear', 'focus_percent', 'alerts_count')
        }),
        ('Metadata', {
            'fields': ('metadata', 'created_at'),
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

@admin.register(BlinkEvent)
class BlinkEventAdmin(admin.ModelAdmin):
    """
    Admin interface options for BlinkEvent model.
    """
    list_display = ('id', 'session_link', 'timestamp_local', 'ear_value_display')
    list_filter = ('session__user', 'timestamp') # Filter by user via session
    search_fields = ('session__id', 'session__user__email')
    readonly_fields = ('timestamp',)
    list_per_page = 50
    ordering = ('-timestamp',)

    def session_link(self, obj):
        """Creates a link to the MonitorSession admin page."""
        link = reverse("admin:monitoring_monitorsession_change", args=[obj.session.id])
        return format_html('<a href="{}">Session {}</a>', link, obj.session.id)
    session_link.short_description = 'Session'
    session_link.admin_order_field = 'session'

    def timestamp_local(self, obj):
        """Displays timestamp in local timezone."""
        return obj.timestamp.astimezone().strftime('%d/%m/%Y %H:%M:%S.%f')[:-3] # Include milliseconds
    timestamp_local.short_description = 'Timestamp (Local)'
    timestamp_local.admin_order_field = 'timestamp'

    def ear_value_display(self, obj):
        """Formats EAR value."""
        return f"{obj.ear_value:.3f}" if obj.ear_value is not None else "-"
    ear_value_display.short_description = 'EAR Value'
    ear_value_display.admin_order_field = 'ear_value'


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
            'fields': ('session', 'alert_type')
        }),
        ('Status & Timestamps', {
            'fields': ('triggered_at', 'resolved', 'resolved_at')
        }),
         ('Details', {
            'fields': ('metadata',),
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
