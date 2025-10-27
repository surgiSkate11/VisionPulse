from django.db import models
from django.contrib.auth.models import AbstractUser, Group, Permission, PermissionsMixin, BaseUserManager
from django.db.models import UniqueConstraint
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
import uuid

# =========================
# CHOICES
# =========================
class AccionChoices(models.TextChoices):
    CREATE = 'CREATE', 'Crear'
    UPDATE = 'UPDATE', 'Actualizar'
    DELETE = 'DELETE', 'Eliminar'
    VIEW = 'VIEW', 'Ver'

# =========================
# MODELOS DE MENÚ Y MÓDULOS
# =========================
class AccionChoices(models.TextChoices):
    CREATE = 'CREATE', 'Crear'
    UPDATE = 'UPDATE', 'Actualizar'
    DELETE = 'DELETE', 'Eliminar'
    VIEW = 'VIEW', 'Ver'

# =========================
# MODELOS DE MENÚ Y MÓDULOS
# =========================
class Menu(models.Model):
    name = models.CharField(verbose_name='Nombre', max_length=150, unique=True)
    icon = models.CharField(verbose_name='Icono (FontAwesome)', max_length=100, default='fas fa-bars')
    order = models.PositiveSmallIntegerField(verbose_name='Orden', default=0)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = 'Menú'
        verbose_name_plural = 'Menús'
        ordering = ['order', 'name']


class Module(models.Model):
    url = models.CharField(
        verbose_name='URL Name',
        max_length=100,
        unique=True,
        help_text="El 'name' de la URL en urls.py. Ej: 'security:home'"
    )
    name = models.CharField(verbose_name='Nombre', max_length=100)
    description = models.TextField(verbose_name='Descripción', blank=True)
    menu = models.ForeignKey(Menu, on_delete=models.PROTECT, verbose_name='Menú', related_name='modules')
    icon = models.CharField(verbose_name='Icono (FontAwesome)', max_length=100, default='fas fa-question-circle')
    is_active = models.BooleanField(verbose_name='Es activo', default=True)
    order = models.PositiveSmallIntegerField(verbose_name='Orden', default=0)
    # El campo 'permissions' en JSON se elimina al ser redundante con el modelo GroupModulePermission

    def __str__(self):
        return f'{self.name} ({self.url})'

    class Meta:
        verbose_name = 'Módulo'
        verbose_name_plural = 'Módulos'
        ordering = ['menu__order', 'order', 'name']


# =========================
# MANAGER Y MODELO DE PERMISOS (CONSOLIDADOS)
# =========================
class GroupModulePermissionManager(models.Manager):
    def get_permissions_for_group(self, group_id):
        """
        Obtiene todos los permisos de módulos activos para un grupo,
        incluyendo toda la información necesaria de módulos y menús.
        """
        return self.filter(
            group_id=group_id,
            module__is_active=True
        ).select_related(
            'module',
            'module__menu'
        ).order_by(
            'module__menu__order',
            'module__order'
        )

class GroupModulePermission(models.Model):
    group = models.ForeignKey(Group, on_delete=models.CASCADE, verbose_name='Grupo', related_name='module_permissions')
    module = models.ForeignKey(Module, on_delete=models.CASCADE, verbose_name='Módulo', related_name='group_permissions')
    objects = GroupModulePermissionManager()

    def __str__(self):
        return f"Permiso: '{self.module.name}' para el grupo '{self.group.name}'"

    class Meta:
        verbose_name = 'Permiso de Módulo por Grupo'
        verbose_name_plural = 'Permisos de Módulos por Grupo'
        ordering = ['group', 'module']
        constraints = [
            UniqueConstraint(fields=['group', 'module'], name='unique_group_module_permission')
        ]


# =========================
# MODELO DE USUARIO (CONSOLIDADO Y CORRECTO)
# =========================
class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('El email es obligatorio')
        email = self.normalize_email(email)
        
        if 'username' not in extra_fields:
            base_username = email.split('@')[0]
            counter = 0
            username = base_username
            while self.model.objects.filter(username=username).exists():
                counter += 1
                username = f"{base_username}{counter}"
            extra_fields['username'] = username

        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        
        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self.create_user(email, password, **extra_fields)


class User(AbstractUser, PermissionsMixin):
    email = models.EmailField('Email', unique=True)
    image = models.ImageField(upload_to='security/users/', max_length=1024, blank=True, null=True)
    
    groups = models.ManyToManyField(
        Group, verbose_name='groups', blank=True,
        help_text='The groups this user belongs to.',
        related_name="custom_user_groups", related_query_name="user"
    )
    user_permissions = models.ManyToManyField(
        Permission, verbose_name='user permissions', blank=True,
        help_text='Specific permissions for this user.',
        related_name="custom_user_permissions", related_query_name="user"
    )
    
    objects = UserManager()
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    # --- Campos de Perfil y Onboarding ---
    bio = models.TextField(max_length=500, blank=True, help_text="Breve descripción sobre ti")
    birth_date = models.DateField(null=True, blank=True)
    city = models.CharField('Ciudad', max_length=200, blank=True, null=True)
    country = models.CharField('País', max_length=100, blank=True, null=True)
    phone = models.CharField('Teléfono', max_length=50, blank=True, null=True)
    profile_completed = models.BooleanField(default=False, help_text="¿Completó el onboarding?")
    
    USER_TYPES = [
        ('office_worker', 'Trabajador de Oficina'), ('programmer', 'Programador'),
        ('designer', 'Diseñador'), ('student', 'Estudiante'), ('gamer', 'Gamer'),
        ('freelancer', 'Freelancer'), ('other', 'Otro'),
    ]
    WORK_ENVIRONMENT = [
        ('office', 'Oficina'), ('home', 'Casa'), ('hybrid', 'Híbrido'),
        ('coworking', 'Coworking'), ('other', 'Otro'),
    ]
    SCREEN_SIZE = [
        ('small', 'Pequeña (< 15")'), ('medium', 'Mediana (15" - 24")'),
        ('large', 'Grande (24" - 32")'), ('ultrawide', 'Ultra ancha (> 32")'),
        ('multiple', 'Múltiples pantallas'),
    ]
    
    user_type = models.CharField(max_length=20, choices=USER_TYPES, default='office_worker', blank=True)
    work_environment = models.CharField(max_length=20, choices=WORK_ENVIRONMENT, default='office', blank=True)
    company = models.CharField(max_length=200, blank=True, help_text="Nombre de tu empresa u organización")
    job_title = models.CharField(max_length=200, blank=True, help_text="Tu puesto o rol profesional")
    screen_size = models.CharField(max_length=20, choices=SCREEN_SIZE, default='medium', blank=True)
    preferred_work_time = models.CharField(
        max_length=20,
        choices=[('morning', 'Mañana'), ('afternoon', 'Tarde'), ('evening', 'Noche'), ('late_night', 'Madrugada')],
        default='morning', blank=True, help_text="Horario donde más trabajas frente a la pantalla"
    )

    # --- Campos de Configuración: Métricas de Ojos ---
    ear_threshold = models.FloatField(
        "Umbral EAR", 
        default=0.20, 
        validators=[MinValueValidator(0.05), MaxValueValidator(0.40)],
        help_text="Sensibilidad de apertura ocular (EAR). Más bajo = más sensible."
    )
    fatigue_threshold = models.FloatField(
        "Factor Fatiga (EAR %)", 
        default=0.7, 
        validators=[MinValueValidator(0.1), MaxValueValidator(1.0)], 
        help_text="Porcentaje del EAR base para alerta de fatiga (ej: 0.7 = 70% de tu EAR normal)."
    )
    microsleep_duration_seconds = models.FloatField(
        "Duración Microsueño (seg)",
        default=1.5, 
        validators=[MinValueValidator(0.8), MaxValueValidator(5.0)], 
        help_text="Segundos con ojos cerrados para disparar alerta de microsueño. (Peligro: >1 seg)"
    )
    blink_window_frames = models.PositiveSmallIntegerField(
        "Ventana confirmación (frames)", 
        default=3, 
        validators=[MinValueValidator(1), MaxValueValidator(10)],
        help_text="Frames consecutivos con ojos cerrados para confirmar un parpadeo."
    )
    
    # --- Campos de Configuración: Tasa de Parpadeo ---
    low_blink_rate_threshold = models.PositiveSmallIntegerField(
        "Umbral Parpadeo Bajo (por min)",
        default=10, 
        validators=[MinValueValidator(3), MaxValueValidator(20)], 
        help_text="Alertar si parpadea MENOS de X veces por minuto. (Normal: 15-20, Concentración: 3-8)"
    )
    high_blink_rate_threshold = models.PositiveSmallIntegerField(
        "Umbral Parpadeo Alto (por min)",
        default=35, 
        validators=[MinValueValidator(25), MaxValueValidator(60)], 
        help_text="Alertar si parpadea MÁS de X veces por minuto. (Normal: 15-20, Estrés: >30)"
    )
    
    # --- Campos de Configuración: Boca y Bostezos ---
    yawn_mar_threshold = models.FloatField(
        "Umbral Bostezo (MAR)",
        default=0.6, 
        validators=[MinValueValidator(0.4), MaxValueValidator(1.0)], 
        help_text="Sensibilidad de detección de bostezo (proporción de apertura de boca)."
    )
    
    # --- Campos de Configuración: Pose de Cabeza (Distracción y Postura) ---
    distraction_angle_threshold = models.PositiveSmallIntegerField(
        "Ángulo de Distracción (°)",
        default=25, 
        validators=[MinValueValidator(10), MaxValueValidator(45)], 
        help_text="Ángulo (grados) de desviación de la cabeza para considerarse 'distraído'."
    )
    postural_rigidity_duration_seconds = models.PositiveSmallIntegerField(
        "Duración Rigidez Postural (seg)",
        default=180, 
        validators=[MinValueValidator(60), MaxValueValidator(600)], 
        help_text="Tiempo (segundos) sin mover la cabeza para alertar sobre rigidez."
    )
    
    # --- Campos de Configuración: Ambiente ---
    low_light_threshold = models.PositiveSmallIntegerField(
        "Umbral Luz Baja (Luminancia)",
        default=70, 
        validators=[MinValueValidator(30), MaxValueValidator(120)], 
        help_text="Nivel de brillo (0-255) por debajo del cual se considera 'Iluminación Baja'."
    )
    
    # --- Campos de Configuración: Sistema de Monitoreo ---
    monitoring_frequency = models.PositiveIntegerField(
        "Frecuencia de análisis (seg)", 
        default=30, 
        validators=[MinValueValidator(10), MaxValueValidator(300)], 
        help_text="Frecuencia de análisis visual profundo en segundos."
    )
    break_reminder_interval = models.PositiveIntegerField(
        "Recordatorio Descanso (min)", 
        default=20, 
        validators=[MinValueValidator(5), MaxValueValidator(120)], 
        help_text="Intervalo para recordatorios de descanso en minutos."
    )
    face_detection_sensitivity = models.FloatField(
        "Sensibilidad Detección Facial", 
        default=0.7, 
        validators=[MinValueValidator(0.1), MaxValueValidator(1.0)], 
        help_text="Sensibilidad de detección facial (0.1-1.0)."
    )
    sampling_interval_seconds = models.PositiveIntegerField(
        "Intervalo Muestreo (seg)",
        default=5, 
        validators=[MinValueValidator(1), MaxValueValidator(60)],
        help_text="Intervalo de captura de frames para análisis."
    )
    camera_enabled = models.BooleanField(
        "Cámara Habilitada",
        default=True,
        help_text="Habilitar o deshabilitar el uso de la cámara."
    )
    
    # --- Campos de Configuración: Overlay Facial (Rendimiento) ---
    face_overlay_enabled = models.BooleanField(
        "Overlay Facial Habilitado",
        default=True,
        help_text="Mostrar el óvalo verde sobre el rostro detectado. Desactivar en dispositivos de gama baja."
    )
    face_overlay_glow_intensity = models.FloatField(
        "Intensidad Brillo Overlay",
        default=0.6,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text="Intensidad del brillo del óvalo facial (0.0-1.0). Menor valor = menos GPU."
    )
    face_overlay_blur_sigma = models.PositiveSmallIntegerField(
        "Sigma Desenfoque Overlay",
        default=9,
        validators=[MinValueValidator(1), MaxValueValidator(20)],
        help_text="Cantidad de desenfoque del glow (1-20). Menor valor = más rápido."
    )

    # --- Campos de Configuración: Interfaz y Notificaciones ---
    dark_mode = models.BooleanField("Modo Oscuro", default=False)
    notification_mode = models.CharField(
        "Modo de Notificación",
        max_length=10, 
        choices=[
            ('visual', 'Visual'), 
            ('sound', 'Sonora'), 
            ('both', 'Ambos'), 
            ('none', 'Ninguno')
        ], 
        default='both'
    )
    alert_volume = models.FloatField(
        "Volumen de Alertas",
        default=0.5, 
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text="Volumen de las alertas sonoras (0.0-1.0)."
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
    
    # --- Campos de Configuración: Privacidad y Datos ---
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
    
    # --- Campos de Configuración: Localización ---
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

    # --- Campos de Estadísticas de Salud Visual ---
    total_monitoring_time = models.PositiveIntegerField(default=0, help_text="Tiempo total monitoreado en minutos")
    total_sessions = models.PositiveIntegerField(default=0, help_text="Número total de sesiones de monitoreo")
    current_streak = models.PositiveIntegerField(default=0, help_text="Días consecutivos usando la aplicación")
    longest_streak = models.PositiveIntegerField(default=0)
    last_streak_update = models.DateField(null=True, blank=True)
    exercises_completed = models.PositiveIntegerField(default=0, help_text="Ejercicios oculares completados")
    # breaks_taken eliminado: era redundante con exercises_completed
    fatigue_episodes = models.PositiveIntegerField(default=0, help_text="Episodios de fatiga detectados")
    email_notifications = models.BooleanField(default=True)

    # --- Timestamps y UUIDs ---
    user_uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.get_full_name() or self.username

    def update_monitoring_stats(self):
        """
        Actualiza las estadísticas de monitoreo del usuario.
        Debe llamarse después de completar una sesión.
        """
        from apps.monitoring.models import MonitorSession
        from django.db.models import Sum, Count
        
        completed_sessions = MonitorSession.objects.filter(
            user=self,
            status='completed'
        )
        
        # Total de sesiones
        self.total_sessions = completed_sessions.count()
        
        # Tiempo total de monitoreo
        total_duration = completed_sessions.aggregate(
            total=Sum('total_duration')
        )['total'] or 0
        
        if total_duration == 0:
            total_duration = completed_sessions.aggregate(
                total=Sum('duration_seconds')
            )['total'] or 0
        
        self.total_monitoring_time = int(total_duration / 60) if total_duration else 0
        
        self.save(update_fields=['total_sessions', 'total_monitoring_time'])
    
    def update_exercise_stats(self):
        """
        Actualiza las estadísticas de ejercicios del usuario.
        """
        from apps.exercises.models import ExerciseSession
        
        self.exercises_completed = ExerciseSession.objects.filter(
            user=self,
            completed=True
        ).count()
        
        self.save(update_fields=['exercises_completed'])
    
    def update_fatigue_stats(self):
        """
        Actualiza las estadísticas de fatiga del usuario.
        """
        from apps.monitoring.models import AlertEvent
        
        self.fatigue_episodes = AlertEvent.objects.filter(
            session__user=self,
            alert_type='fatigue'
        ).count()
        
        self.save(update_fields=['fatigue_episodes'])
    
    def update_streak(self):
        """
        Actualiza la racha de días consecutivos del usuario.
        """
        from apps.monitoring.models import MonitorSession
        from django.db.models import Count
        from datetime import date, timedelta
        
        today = date.today()
        
        # Si ya se actualizó hoy, no hacer nada
        if self.last_streak_update and self.last_streak_update >= today:
            return
        
        # Obtener sesiones completadas agrupadas por fecha
        sessions_by_date = MonitorSession.objects.filter(
            user=self,
            status='completed'
        ).values('start_time__date').annotate(
            count=Count('id')
        ).order_by('-start_time__date')
        
        if not sessions_by_date.exists():
            self.current_streak = 0
            self.last_streak_update = today
            self.save(update_fields=['current_streak', 'last_streak_update'])
            return
        
        dates_with_sessions = [item['start_time__date'] for item in sessions_by_date]
        
        # Calcular racha actual
        current_streak = 0
        check_date = today
        
        # Revisar si hay sesión hoy o ayer
        if today not in dates_with_sessions and (today - timedelta(days=1)) not in dates_with_sessions:
            current_streak = 0
        else:
            for session_date in dates_with_sessions:
                if session_date == check_date:
                    current_streak += 1
                    check_date = check_date - timedelta(days=1)
                elif session_date == check_date - timedelta(days=1):
                    current_streak += 1
                    check_date = session_date - timedelta(days=1)
                else:
                    break
        
        self.current_streak = current_streak
        
        # Actualizar racha más larga
        if current_streak > self.longest_streak:
            self.longest_streak = current_streak
        
        self.last_streak_update = today
        self.save(update_fields=['current_streak', 'longest_streak', 'last_streak_update'])


# =========================
# OTROS MODELOS
# =========================

class AuditUser(models.Model):
    usuario = models.ForeignKey(User, verbose_name='Usuario', on_delete=models.PROTECT)
    tabla = models.CharField(max_length=100, verbose_name='Tabla')
    registroid = models.IntegerField(verbose_name='Registro Id')
    accion = models.CharField(choices=AccionChoices.choices, max_length=15, verbose_name='Accion')
    fecha = models.DateField(verbose_name='Fecha', default=timezone.now)
    hora = models.TimeField(verbose_name='Hora', default=timezone.now)
    estacion = models.CharField(max_length=100, verbose_name='Estacion')

    def __str__(self):
        return f"{self.usuario.username} - {self.tabla} [{self.accion}]"

    class Meta:
        verbose_name = 'Auditoria de Usuario'
        verbose_name_plural = 'Auditorias de Usuarios'
        ordering = ('-fecha', '-hora')


class NotificationPreference(models.Model):
    CHANNELS = [('email', 'Email'), ('webpush', 'WebPush'), ('sound', 'Sonido')]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notification_prefs')
    channel = models.CharField(max_length=20, choices=CHANNELS)
    enabled = models.BooleanField(default=True)
    quiet_hours_start = models.TimeField(null=True, blank=True)
    quiet_hours_end = models.TimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'channel')
        verbose_name = 'Preferencia de Notificación'
        verbose_name_plural = 'Preferencias de Notificación'

    def __str__(self):
        return f"{self.user.username} - {self.channel}"


class CameraDevice(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='camera_devices')
    name = models.CharField(max_length=120)
    device_id = models.CharField(max_length=300)
    is_default = models.BooleanField(default=False)
    last_used = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'device_id')
        indexes = [models.Index(fields=['user', 'is_default'])]
        ordering = ['-is_default', 'name']
        verbose_name = 'Dispositivo de Cámara'
        verbose_name_plural = 'Dispositivos de Cámara'

    def __str__(self):
        return f"{self.name} ({self.user.username})"


class ConsentRecord(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='consents')
    given = models.BooleanField(default=False)
    timestamp = models.DateTimeField(default=timezone.now)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=512, blank=True)
    policy_version = models.CharField(max_length=50, default='v1')

    class Meta:
        indexes = [models.Index(fields=['user', 'timestamp'])]
        ordering = ['-timestamp']
        verbose_name = 'Registro de Consentimiento'
        verbose_name_plural = 'Registros de Consentimiento'

    def __str__(self):
        return f"Consent {self.user.username}={self.given} @ {self.timestamp:%Y-%m-%d %H:%M}"