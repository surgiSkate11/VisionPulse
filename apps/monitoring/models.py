from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator, FileExtensionValidator
from django.db import models
from django.utils import timezone


class MonitorSession(models.Model):
    """
    Registro de sesión de monitoreo. No almacena frames, solo métricas agregadas.
    """
    STATUS_CHOICES = [
        ('active', 'Activa'),
        ('paused', 'Pausada'),
        ('completed', 'Completada'),
        ('interrupted', 'Interrumpida'),
    ]
    
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='monitor_sessions')
    camera = models.ForeignKey('security.CameraDevice', on_delete=models.SET_NULL, null=True, blank=True)
    
    # Tiempos
    start_time = models.DateTimeField(default=timezone.now)
    end_time = models.DateTimeField(null=True, blank=True)
    
    # Duraciones (en segundos)
    duration_seconds = models.PositiveIntegerField(null=True, blank=True)
    total_duration = models.FloatField(default=0.0, help_text="Duración total en segundos")
    effective_duration = models.FloatField(default=0.0, help_text="Duración efectiva excluyendo pausas")
    pause_duration = models.FloatField(default=0.0, help_text="Duración total de pausas")
    
    # Métricas de parpadeo
    total_blinks = models.PositiveIntegerField(default=0)
    avg_ear = models.FloatField(null=True, blank=True, validators=[MinValueValidator(0.0), MaxValueValidator(1.0)])
    
    # Métricas de bostezos
    total_yawns = models.PositiveIntegerField(default=0, help_text="Total de bostezos detectados")
    avg_mar = models.FloatField(null=True, blank=True, validators=[MinValueValidator(0.0)], help_text="MAR promedio (Mouth Aspect Ratio)")
    
    # Métricas de postura de cabeza
    avg_head_yaw = models.FloatField(null=True, blank=True, help_text="Yaw promedio en grados")
    avg_head_pitch = models.FloatField(null=True, blank=True, help_text="Pitch promedio en grados")
    avg_head_roll = models.FloatField(null=True, blank=True, help_text="Roll promedio en grados")
    head_pose_variance = models.FloatField(null=True, blank=True, help_text="Varianza de postura de cabeza")
    
    # Métricas de iluminación y calidad
    avg_brightness = models.FloatField(null=True, blank=True, validators=[MinValueValidator(0.0), MaxValueValidator(255.0)])
    detection_rate = models.FloatField(null=True, blank=True, validators=[MinValueValidator(0.0), MaxValueValidator(100.0)], help_text="Porcentaje de frames con detección exitosa")
    
    # Métricas para detección de celular
    phone_detection_count = models.PositiveIntegerField(
        default=0,
        help_text="Número de veces que se detectó uso de celular"
    )
    
    # Métrica de enfoque temporal
    avg_focus_score = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0.0), MaxValueValidator(100.0)],
        help_text="Score promedio de enfoque temporal (%)"
    )
    
    # Métricas de enfoque (ambos campos para compatibilidad)
    focus_percent = models.FloatField(null=True, blank=True, validators=[MinValueValidator(0.0), MaxValueValidator(100.0)])
    focus_score = models.FloatField(null=True, blank=True, validators=[MinValueValidator(0.0), MaxValueValidator(100.0)])
    
    # Alertas (ambos campos para compatibilidad)
    alerts_count = models.PositiveIntegerField(default=0)
    total_alerts = models.PositiveIntegerField(default=0)
    alert_count = models.PositiveIntegerField(default=0)  # Para compatibilidad con templates
    
    # Estado y metadata
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    metadata = models.JSONField(null=True, blank=True, help_text="Metadatos: device info, sampling rate, client-version")
    final_metrics = models.JSONField(null=True, blank=True, help_text="Métricas finales al terminar la sesión")
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['user', 'start_time']),
            models.Index(fields=['created_at']),
            models.Index(fields=['status']),
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

    @property
    def duration_minutes(self):
        """Retorna la duración en minutos"""
        if self.total_duration:
            return self.total_duration / 60
        elif self.duration_seconds:
            return self.duration_seconds / 60
        return 0

    def save(self, *args, **kwargs):
        # Sincronizar campos duplicados
        if self.focus_score is not None and self.focus_percent is None:
            self.focus_percent = self.focus_score
        elif self.focus_percent is not None and self.focus_score is None:
            self.focus_score = self.focus_percent
            
        if self.total_alerts > 0:
            self.alerts_count = self.total_alerts
            self.alert_count = self.total_alerts
        elif self.alerts_count > 0:
            self.total_alerts = self.alerts_count
            self.alert_count = self.alerts_count
            
        if self.start_time and self.end_time and not self.duration_seconds:
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



class AlertEvent(models.Model):
    """
    Eventos de alerta generados por el motor de detección.
    """
    
    # Constantes de tipos de alerta
    ALERT_FATIGUE = 'fatigue'
    ALERT_DISTRACT = 'distraction'
    ALERT_LOW_LIGHT = 'low_light'
    ALERT_MICROSLEEP = 'microsleep'
    ALERT_YAWN = 'yawn'
    ALERT_LOW_BLINK_RATE = 'low_blink_rate'
    ALERT_HIGH_BLINK_RATE = 'high_blink_rate'
    ALERT_FREQUENT_DISTRACT = 'frequent_distraction'
    ALERT_PHONE_USE = 'phone_use'
    ALERT_POSTURAL_RIGIDITY = 'postural_rigidity'
    ALERT_HEAD_AGITATION = 'head_agitation'
    ALERT_DRIVER_ABSENT = 'driver_absent'
    ALERT_MULTIPLE_PEOPLE = 'multiple_people'
    ALERT_CAMERA_OCCLUDED = 'camera_occluded'
    ALERT_CAMERA_LOST = 'camera_lost'
    
    ALERT_TYPES = [
        (ALERT_FATIGUE, 'Fatiga visual'),
        (ALERT_DISTRACT, 'Distracción prolongada'),
        (ALERT_LOW_LIGHT, 'Iluminación baja'),
        (ALERT_MICROSLEEP, 'Microsueño detectado'),
        (ALERT_YAWN, 'Bostezo detectado'),
        (ALERT_LOW_BLINK_RATE, 'Tasa de parpadeo baja'),
        (ALERT_HIGH_BLINK_RATE, 'Tasa de parpadeo alta'),
        (ALERT_FREQUENT_DISTRACT, 'Distracción frecuente (ráfagas)'),
        (ALERT_PHONE_USE, 'Posible uso de celular'),
        (ALERT_POSTURAL_RIGIDITY, 'Rigidez postural / Mirada fija'),
        (ALERT_HEAD_AGITATION, 'Movimiento excesivo de cabeza'),
        (ALERT_DRIVER_ABSENT, 'Usuario ausente'),
        (ALERT_MULTIPLE_PEOPLE, 'Múltiples personas detectadas'),
        (ALERT_CAMERA_OCCLUDED, 'Cámara obstruida'),
        (ALERT_CAMERA_LOST, 'Cámara perdida'),
    ]

    session = models.ForeignKey(MonitorSession, on_delete=models.CASCADE, related_name='alerts')
    alert_type = models.CharField(max_length=30, choices=ALERT_TYPES)
    level = models.CharField(max_length=20, default='medium')  # low, medium, high
    message = models.TextField(blank=True)
    voice_clip = models.FileField(
        'Audio de alerta',
        upload_to='monitoring/alerts/',
        validators=[FileExtensionValidator(allowed_extensions=['mp3', 'wav', 'ogg'])],
        help_text='Audio de voz a reproducir cuando se genera la alerta.',
        max_length=500,
        blank=True,
        null=True,
    )
    triggered_at = models.DateTimeField(default=timezone.now)
    timestamp = models.DateTimeField(default=timezone.now)  # Para compatibilidad
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

    @property
    def type(self):
        """Alias para compatibilidad con templates"""
        return self.alert_type
        
    @property
    def description(self):
        """Retorna la descripción para templates"""
        return self.message or self.get_alert_type_display()

    def mark_resolved(self):
        if not self.resolved:
            self.resolved = True
            self.resolved_at = timezone.now()
            self.save(update_fields=['resolved', 'resolved_at'])

    def __str__(self):
        return f"{self.get_alert_type_display()} ({self.session.user.username}) @ {self.triggered_at:%Y-%m-%d %H:%M}"


class AlertTypeConfig(models.Model):
    """Configuración por tipo de alerta (descripción por defecto y clip de voz)."""
    alert_type = models.CharField(max_length=30, choices=AlertEvent.ALERT_TYPES, unique=True)
    default_voice_clip = models.FileField(
        'Audio por defecto',
        upload_to='monitoring/alerts/types/',
        validators=[FileExtensionValidator(allowed_extensions=['mp3', 'wav', 'ogg'])],
        help_text='Audio por defecto para este tipo de alerta.',
        max_length=500,
        blank=True,
        null=True,
    )
    description = models.CharField('Descripción', max_length=255, blank=True)
    is_active = models.BooleanField('Activo', default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Config Tipo de Alerta'
        verbose_name_plural = 'Configs Tipos de Alerta'
        ordering = ['alert_type']

    def __str__(self):
        return f"{self.get_alert_type_display()}"

# Modelo de configuraciones eliminado - usando solo config predeterminada de OpenCV


# =========================
# Helper para obtener configuración efectiva
# =========================
def get_effective_detection_config(user) -> dict:
    """
    Retorna la configuración básica del usuario.
    Solo usa configuraciones predeterminadas de OpenCV para métricas exactas.
    """
    return {
        'ear_threshold': getattr(user, 'ear_threshold', 0.20),
        'microsleep_duration_seconds': getattr(user, 'microsleep_duration_seconds', 1.5),
        'blink_window_frames': getattr(user, 'blink_window_frames', 3),
        'low_blink_rate_threshold': getattr(user, 'low_blink_rate_threshold', 10),
        'high_blink_rate_threshold': getattr(user, 'high_blink_rate_threshold', 35),
        'yawn_mar_threshold': getattr(user, 'yawn_mar_threshold', 0.6),
        'distraction_angle_threshold': getattr(user, 'distraction_angle_threshold', 25),
        'postural_rigidity_duration_seconds': getattr(user, 'postural_rigidity_duration_seconds', 180),
        'low_light_threshold': getattr(user, 'low_light_threshold', 70),
        'face_detection_sensitivity': getattr(user, 'face_detection_sensitivity', 0.7),
        'monitoring_frequency': getattr(user, 'monitoring_frequency', 30),
        'sampling_interval_seconds': getattr(user, 'sampling_interval_seconds', 5),
    }
