from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.utils import timezone


class MonitorSession(models.Model):
    """
    Registro de sesión de monitoreo. No almacena frames, solo métricas agregadas.
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='monitor_sessions')
    camera = models.ForeignKey('security.CameraDevice', on_delete=models.SET_NULL, null=True, blank=True)
    start_time = models.DateTimeField(default=timezone.now)
    end_time = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.PositiveIntegerField(null=True, blank=True)
    total_blinks = models.PositiveIntegerField(default=0)
    avg_ear = models.FloatField(null=True, blank=True, validators=[MinValueValidator(0.0), MaxValueValidator(1.0)])
    focus_percent = models.FloatField(null=True, blank=True, validators=[MinValueValidator(0.0), MaxValueValidator(100.0)])  # porcentaje 0-100
    alerts_count = models.PositiveIntegerField(default=0)
    metadata = models.JSONField(null=True, blank=True, help_text="Metadatos: device info, sampling rate, client-version")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['user', 'start_time']),
            models.Index(fields=['created_at']),
        ]
        ordering = ['-start_time']
        verbose_name = 'Sesión de Monitoreo'
        verbose_name_plural = 'Sesiones de Monitoreo'

    def calculate_active_duration(self):
        """Calcula la duración activa excluyendo las pausas"""
        if not self.end_time:
            return 0
            
        total_duration = (self.end_time - self.start_time).total_seconds()
        paused_duration = sum(
            (pause.resume_time - pause.pause_time).total_seconds()
            for pause in self.pauses.all()
            if pause.resume_time  # Solo contar pausas que fueron reanudadas
        )
        return int(total_duration - paused_duration)

    def save(self, *args, **kwargs):
        if self.start_time and self.end_time:
            self.duration_seconds = self.calculate_active_duration()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Session {self.user.username} [{self.start_time:%Y-%m-%d %H:%M}]"


class SessionPause(models.Model):
    """
    Registra los intervalos de pausa durante una sesión de monitoreo.
    """
    session = models.ForeignKey(MonitorSession, on_delete=models.CASCADE, related_name='pauses')
    pause_time = models.DateTimeField(default=timezone.now)
    resume_time = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['session', 'pause_time']),
        ]
        ordering = ['pause_time']
        verbose_name = 'Pausa de Sesión'
        verbose_name_plural = 'Pausas de Sesión'

    def __str__(self):
        duration = "En curso" if not self.resume_time else f"{int((self.resume_time - self.pause_time).total_seconds())}s"
        return f"Pausa en {self.pause_time:%H:%M:%S} [{duration}]"

class BlinkEvent(models.Model):
    """
    Registro opcional de cada parpadeo detectado. Puede generar volumen alto; usar solo si necesario.
    """
    session = models.ForeignKey(MonitorSession, on_delete=models.CASCADE, related_name='blink_events')
    timestamp = models.DateTimeField(default=timezone.now)
    duration_ms = models.PositiveIntegerField(null=True, blank=True, validators=[MinValueValidator(0)])
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['session', 'timestamp']),
        ]
        ordering = ['timestamp']
        verbose_name = 'Evento de Parpadeo'
        verbose_name_plural = 'Eventos de Parpadeo'

    def __str__(self):
        return f"Blink {self.session.user.username} @ {self.timestamp:%H:%M:%S}"


class AlertEvent(models.Model):
    """
    Eventos de alerta generados por el motor de detección.
    """
    ALERT_FATIGUE = 'fatigue'
    ALERT_DISTRACT = 'distract'
    ALERT_LOW_LIGHT = 'low_light'
    ALERT_CAMERA_LOST = 'camera_lost'
    ALERT_TYPES = [
        (ALERT_FATIGUE, 'Fatiga visual'),
        (ALERT_DISTRACT, 'Distracción prolongada'),
        (ALERT_LOW_LIGHT, 'Iluminación baja'),
        (ALERT_CAMERA_LOST, 'Cámara perdida'),
    ]

    session = models.ForeignKey(MonitorSession, on_delete=models.CASCADE, related_name='alerts')
    alert_type = models.CharField(max_length=30, choices=ALERT_TYPES)
    triggered_at = models.DateTimeField(default=timezone.now)
    resolved = models.BooleanField(default=False)
    resolved_at = models.DateTimeField(null=True, blank=True)
    metadata = models.JSONField(null=True, blank=True, help_text="Detalles: avg_ear, window_frames, sample_rate")

    class Meta:
        indexes = [
            models.Index(fields=['session', 'alert_type', 'triggered_at']),
        ]
        ordering = ['-triggered_at']
        verbose_name = 'Evento de Alerta'
        verbose_name_plural = 'Eventos de Alerta'

    def mark_resolved(self):
        if not self.resolved:
            self.resolved = True
            self.resolved_at = timezone.now()
            self.save(update_fields=['resolved', 'resolved_at'])

    def __str__(self):
        return f"{self.get_alert_type_display()} ({self.session.user.username}) @ {self.triggered_at:%Y-%m-%d %H:%M}"
