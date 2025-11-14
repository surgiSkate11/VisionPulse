from django.conf import settings
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator

# =========================
# MODELO DE CONFIGURACIÓN DE MONITOREO POR USUARIO
# =========================
class UserMonitoringConfig(models.Model):
    """
    Almacena las preferencias de monitoreo y alertas de un usuario.
    Separa la configuración del modelo User.
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='monitoring_config'
    )

    # --- CAMPOS DE ALERTAS Y COMPORTAMIENTO ---
    
    # --- Configuración: Métricas de Ojos ---
    ear_threshold = models.FloatField(
        "Umbral EAR (Eye Aspect Ratio)", 
        default=0.20, 
        validators=[MinValueValidator(0.05), MaxValueValidator(0.40)],
        help_text="Sensibilidad de apertura ocular. Más bajo = más sensible. (0.05 - 0.40)"
    )
    
    # --- Configuración de Microsueño ---
    
    microsleep_duration_seconds = models.FloatField(
        "Duración Microsueño (seg)",
        default=5.0,
        validators=[MinValueValidator(5.0), MaxValueValidator(15.0)]
    )

    def clean(self):
        super().clean()
        # Validación local sin depender de configuración global por tipo
        min_val = 5.0
        max_val = 15.0
        if self.microsleep_duration_seconds is not None:
            if not (min_val <= self.microsleep_duration_seconds <= max_val):
                from django.core.exceptions import ValidationError
                raise ValidationError({'microsleep_duration_seconds': f'Debe estar entre {min_val} y {max_val} segundos.'})
    
    low_blink_rate_threshold = models.PositiveSmallIntegerField(
        "Umbral Parpadeo Bajo (por min)",
        default=10,
        validators=[MinValueValidator(3), MaxValueValidator(14)],
        help_text="Por debajo de 10 PPM se considera bajo. (3-14 PPM)"
    )
    high_blink_rate_threshold = models.PositiveSmallIntegerField(
        "Umbral Parpadeo Alto (por min)",
        default=25,
        validators=[MinValueValidator(21), MaxValueValidator(60)],
        help_text="Por encima de 20-25 PPM se considera alto. (21-60 PPM)"
    )
    low_light_threshold = models.PositiveSmallIntegerField(
        "Umbral Luz Baja (Luminancia)",
        default=70,
        validators=[MinValueValidator(30), MaxValueValidator(120)]
    )
    monitoring_frequency = models.PositiveIntegerField(
        "Frecuencia de análisis (seg)",
        default=30,
        validators=[MinValueValidator(10), MaxValueValidator(300)]
    )
    break_reminder_interval = models.PositiveIntegerField(
        "Recordatorio Descanso (min)",
        default=20,
        validators=[MinValueValidator(5), MaxValueValidator(120)]
    )
    sampling_interval_seconds = models.PositiveIntegerField(
        "Intervalo Muestreo (seg)",
        default=5,
        validators=[MinValueValidator(1), MaxValueValidator(60)]
    )
    camera_enabled = models.BooleanField(
        "Cámara Habilitada",
        default=True,
        help_text="Habilitar o deshabilitar el uso de la cámara."
    )

    # --- Detección, Resolución, Repetición y Umbrales (por usuario) ---
    detection_delay_seconds = models.PositiveIntegerField(
        'Retraso de Detección (seg)',
        default=5,
        validators=[MinValueValidator(1), MaxValueValidator(3600)],
        help_text='Tiempo que debe mantenerse la condición antes de activar la alerta'
    )
    hysteresis_timeout_seconds = models.PositiveIntegerField(
        'Tiempo de Histéresis (seg)',
        default=30,
        validators=[MinValueValidator(5), MaxValueValidator(3600)],
        help_text='Tiempo que debe mantenerse la condición OK para considerar resuelta (histéresis)'
    )
    alert_cooldown_seconds = models.PositiveIntegerField(
        'Cooldown de Alertas (seg)',
        default=60,
        validators=[MinValueValidator(5), MaxValueValidator(3600)],
        help_text='Tiempo mínimo entre alertas del mismo tipo para el usuario'
    )
    
    # --- CONFIGURACIÓN DE REPETICIÓN DE ALERTAS ---
    alert_repeat_interval = models.PositiveIntegerField(
        "Intervalo Repetición Alertas (seg)",
        default=5,
        validators=[MinValueValidator(1), MaxValueValidator(50)],
        help_text="Tiempo en segundos para que la alerta vuelva a sonar hasta que sea resuelta (1-50 s)"
    )
    repeat_max_per_hour = models.PositiveIntegerField(
        "Máximo Repeticiones por Hora",
        default=12,
        validators=[MinValueValidator(1), MaxValueValidator(60)],
        help_text="Número máximo de veces que una alerta puede repetirse en una hora"
    )
    
    # --- Notificaciones, UI, Privacidad, etc. ---
    dark_mode = models.BooleanField("Modo Oscuro", default=False)
    alert_volume = models.FloatField(
        "Volumen de Alertas",
        default=0.5,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)]
    )
    notify_inactive_tab = models.BooleanField(
        "Notificar en Tab Inactiva",
        default=True,
        help_text="Mostrar notificaciones cuando la pestaña no está activa."
    )
    email_notifications = models.BooleanField(
        "Notificaciones por Email",
        default=True,
        help_text="Recibir notificaciones por correo electrónico."
    )
    data_collection_consent = models.BooleanField(
        "Consentimiento Recolección Datos",
        default=False,
        help_text="Autorizar recolección de datos para mejorar el servicio."
    )
    anonymous_analytics = models.BooleanField(
        "Analíticas Anónimas",
        default=True,
        help_text="Permitir analíticas anónimas para estadísticas generales."
    )
    locale = models.CharField(
        "Idioma/Localización",
        max_length=10,
        default='es',
        blank=True,
        help_text="Código de idioma (ej: 'es', 'en', 'fr')."
    )
    timezone = models.CharField(
        "Zona horaria",
        max_length=50,
        default='America/Guayaquil',
        blank=True,
        help_text="Zona horaria del usuario (ej: 'America/Guayaquil')."
    )

    def __str__(self):
        return f"Configuración de {self.user.username}"
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
    
    
    # Métricas de postura de cabeza
    
    # Métricas de iluminación y calidad
    avg_brightness = models.FloatField(null=True, blank=True, validators=[MinValueValidator(0.0), MaxValueValidator(255.0)])
    detection_rate = models.FloatField(null=True, blank=True, validators=[MinValueValidator(0.0), MaxValueValidator(100.0)], help_text="Porcentaje de frames con detección exitosa")
    
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
    
    # Contador de alertas
    alert_count = models.PositiveIntegerField(default=0, help_text="Número total de alertas durante la sesión")
    
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
        # Sincronizar campos duplicados de focus
        if self.focus_score is not None and self.focus_percent is None:
            self.focus_percent = self.focus_score
        elif self.focus_percent is not None and self.focus_score is None:
            self.focus_score = self.focus_percent
            
        # Calcular duración si no existe
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
    def save(self, *args, **kwargs):
        # Si resolved_at está presente, siempre marca resolved=True
        if self.resolved_at:
            self.resolved = True
        elif self.resolved:
            # Si resolved se marca manualmente, poner resolved_at si no existe
            if not self.resolved_at:
                self.resolved_at = timezone.now()
        super().save(*args, **kwargs)
    """
    Eventos de alerta generados por el motor de detección.
    """
    
    # Constantes de tipos de alerta
    ALERT_FATIGUE = 'fatigue'
    ALERT_DISTRACT = 'distraction'
    ALERT_LOW_LIGHT = 'low_light'
    ALERT_MICROSLEEP = 'microsleep'
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
    ALERT_HEAD_TENSION = 'head_tension'
    ALERT_MICRO_RHYTHM = 'micro_rhythm'
    ALERT_BAD_POSTURE = 'bad_posture'
    ALERT_BAD_DISTANCE = 'bad_distance'
    ALERT_STRONG_GLARE = 'strong_glare'
    ALERT_LOW_LIGHT = 'low_light'
    ALERT_STRONG_LIGHT = 'strong_light'
    ALERT_BREAK_REMINDER = 'break_reminder'  # 🔥 NUEVO: Recordatorio de descanso
    
    ALERT_TYPES = [
        (ALERT_FATIGUE, 'Fatiga visual'),
        (ALERT_DISTRACT, 'Distracción prolongada'),
        (ALERT_LOW_LIGHT, 'Iluminación baja'),
        (ALERT_MICROSLEEP, 'Microsueño detectado'),
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
        (ALERT_HEAD_TENSION, 'Tensión en cuello'),
        (ALERT_MICRO_RHYTHM, 'Somnolencia temprana'),
        (ALERT_BAD_POSTURE, 'Postura incorrecta'),
        (ALERT_BAD_DISTANCE, 'Distancia incorrecta'),
        (ALERT_STRONG_GLARE, 'Reflejo excesivo'),
        (ALERT_STRONG_LIGHT, 'Luz excesiva'),
        (ALERT_BREAK_REMINDER, 'Recordatorio de descanso')  # 🔥 NUEVO
    ]

    session = models.ForeignKey(MonitorSession, on_delete=models.CASCADE, related_name='alerts')
    alert_type = models.CharField(max_length=30, choices=ALERT_TYPES)
    level = models.CharField(max_length=20, default='medium')  # low, medium, high, critical
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
    
    # 🔥 NUEVOS CAMPOS para gestión de ejercicios
    exercise_session = models.ForeignKey(
        'exercises.ExerciseSession',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='related_alert',
        verbose_name='Sesión de Ejercicio',
        help_text='Sesión de ejercicio realizada para resolver esta alerta'
    )
    auto_resolved = models.BooleanField(
        default=False,
        verbose_name='Auto-resuelta',
        help_text='True si se resolvió automáticamente sin intervención del usuario'
    )
    resolution_method = models.CharField(
        max_length=20,
        choices=[
            ('ack', 'Reconocida/Cerrada'),
            ('exercise', 'Ejercicio Completado'),
            ('dismissed', 'Descartada por el usuario'),
            ('timeout', 'Auto-cerrada por timeout'),
            ('improved', 'Condición mejorada automáticamente'),
            ('auto', 'Auto-resuelta')
        ],
        null=True,
        blank=True,
        verbose_name='Método de Resolución'
    )
    
    # Campos para gestión de repetición
    repeat_count = models.PositiveIntegerField(
        'Número de Repeticiones',
        default=0,
        help_text='Cuántas veces se ha repetido esta alerta'
    )
    last_repeated_at = models.DateTimeField(
        'Última Repetición',
        null=True,
        blank=True,
        help_text='Timestamp de la última vez que se repitió'
    )

    class Meta:
        indexes = [
            models.Index(fields=['session', 'alert_type', 'triggered_at']),
            models.Index(fields=['triggered_at']),
            models.Index(fields=['session', 'triggered_at']),
            models.Index(fields=['alert_type', 'triggered_at']),
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

    def mark_resolved(self, method=None, is_auto=False):
        """
        Marca una alerta como resuelta. 
        
        Args:
            method (str): Método de resolución (exercise, improved, etc)
            is_auto (bool): True si se resolvió automáticamente 
        """
        self.resolved = True
        self.resolved_at = timezone.now()
        self.resolution_method = method
        self.auto_resolved = is_auto
        
        self.save(update_fields=['resolved', 'resolved_at', 'resolution_method', 'auto_resolved'])

    def __str__(self):
        return f"{self.get_alert_type_display()} ({self.session.user.username}) @ {self.triggered_at:%Y-%m-%d %H:%M}"


class AlertTypeConfig(models.Model):
    """Configuración por tipo de alerta: solo título/etiqueta, descripción y audio por defecto."""
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
    metadata = models.JSONField(
        null=True,
        blank=True,
        help_text='Metadatos adicionales (no umbrales/tiempos)'
    )

    class Meta:
        verbose_name = 'Config Tipo de Alerta'
        verbose_name_plural = 'Configs Tipos de Alerta'
        ordering = ['alert_type']

    def __str__(self):
        return f"{self.get_alert_type_display()}"


# =========================
# MODELO DE MAPEO ALERTA-EJERCICIO
# =========================
class AlertExerciseMapping(models.Model):
    """
    Mapeo de qué ejercicio corresponde a cada tipo de alerta.
    No todas las alertas tienen ejercicio asociado.
    """
    alert_type = models.CharField(
        max_length=30,
        choices=AlertEvent.ALERT_TYPES,
        unique=True,
        verbose_name='Tipo de Alerta'
    )
    exercise = models.ForeignKey(
        'exercises.Exercise',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='alert_mappings',
        verbose_name='Ejercicio Recomendado'
    )
    is_active = models.BooleanField(
        'Activo',
        default=True,
        help_text='Si está inactivo, no se sugerirá el ejercicio para esta alerta'
    )
    priority = models.PositiveSmallIntegerField(
        'Prioridad',
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(10)],
        help_text='1 = Máxima prioridad, 10 = Mínima prioridad'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Mapeo Alerta-Ejercicio'
        verbose_name_plural = 'Mapeos Alerta-Ejercicio'
        ordering = ['priority', 'alert_type']

    def __str__(self):
        exercise_name = self.exercise.title if self.exercise else 'Sin ejercicio'
        return f"{self.get_alert_type_display()} → {exercise_name}"


# =========================
# Helper para obtener configuración efectiva
# =========================
def get_effective_detection_config(user) -> dict:
    """
    Retorna la configuración básica del usuario.
    Solo usa configuraciones predeterminadas de OpenCV para métricas exactas.
    """
    user_config = getattr(user, 'monitoring_config', None)

    # Obtener configuración de microsueño del usuario, con validación de rango 5.0-15.0
    microsleep_duration = 5.0
    if user_config and user_config.microsleep_duration_seconds is not None:
        ms = float(user_config.microsleep_duration_seconds)
        microsleep_duration = ms if 5.0 <= ms <= 15.0 else 5.0

    # Construir configuración efectiva priorizando configuración por usuario
    return {
        'ear_threshold': (user_config.ear_threshold if user_config else 0.20),
        'microsleep_duration_seconds': microsleep_duration,
        'low_blink_rate_threshold': (user_config.low_blink_rate_threshold if user_config else 10),
        'high_blink_rate_threshold': (user_config.high_blink_rate_threshold if user_config else 35),
        'low_light_threshold': (user_config.low_light_threshold if user_config else 70),
        'monitoring_frequency': (user_config.monitoring_frequency if user_config else 30),
        'sampling_interval_seconds': (user_config.sampling_interval_seconds if user_config else 5),
        # Nuevos campos por-usuario
        'detection_delay_seconds': (user_config.detection_delay_seconds if user_config else 5),
        'hysteresis_timeout_seconds': (user_config.hysteresis_timeout_seconds if user_config else 30),
        'alert_cooldown_seconds': (user_config.alert_cooldown_seconds if user_config else 60),
    }
