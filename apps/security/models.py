from django.db import models
from django.contrib.auth.models import AbstractUser, Group, Permission, PermissionsMixin, BaseUserManager
from django.db.models import UniqueConstraint
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
import uuid

# Choices para auditoría
class AccionChoices(models.TextChoices):
    CREATE = 'CREATE', 'Crear'
    UPDATE = 'UPDATE', 'Actualizar'
    DELETE = 'DELETE', 'Eliminar'
    VIEW = 'VIEW', 'Ver'

# Modelo de usuario personalizado para VisionPulse
# (mantenemos el sistema de menús y módulos para administración)

# =========================
# MODELO: Menu
# =========================
"""
Modelo Menu: Representa las categorías principales de navegación del sistema.
Cada menú agrupa varios módulos relacionados funcionalmente.

Ejemplos:
1. Monitoreo (icon: bi bi-eye, order: 1) - Agrupa módulos de sesiones, alertas, estadísticas
2. Ejercicios (icon: bi bi-heart-pulse, order: 2) - Agrupa módulos de ejercicios oculares, rutinas
3. Configuración (icon: bi bi-gear, order: 3) - Agrupa módulos de configuración y preferencias
"""
class Menu(models.Model):
    name = models.CharField(verbose_name='Nombre', max_length=150, unique=True)
    icon = models.CharField(verbose_name='Icono', max_length=100, default='bi bi-calendar-x-fill')
    order = models.PositiveSmallIntegerField(verbose_name='Orden', default=0)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = 'Menu'
        verbose_name_plural = 'Menus'
        ordering = ['order', 'name']

# =========================
# MODELO: Module
# =========================
"""
Modelo Module: Representa funcionalidades específicas del sistema agrupadas por menú.
Cada módulo tiene una URL única y pertenece a un menú particular.

Ejemplos:
1. Sesiones (url: sesiones/, menu: Monitoreo) - Historial de sesiones de monitoreo
2. Alertas (url: alertas/, menu: Monitoreo) - Gestión de alertas de fatiga
3. Ejercicios (url: ejercicios/, menu: Ejercicios) - Catálogo de ejercicios oculares
"""
class Module(models.Model):
    url = models.CharField(verbose_name='Url', max_length=100, unique=True)
    name = models.CharField(verbose_name='Nombre', max_length=100)
    # La relación ForeignKey con el modelo Menu indica una relación de una a muchos en la que
    # un menú puede tener múltiples módulos, pero cada módulo pertenece a un solo menú.
    menu = models.ForeignKey(Menu, on_delete=models.PROTECT, verbose_name='Menu', related_name='modules')
    description = models.CharField(verbose_name='Descripción', max_length=200, null=True, blank=True)
    icon = models.CharField(verbose_name='Icono', max_length=100, default='bi bi-x-octagon')
    is_active = models.BooleanField(verbose_name='Es activo', default=True)
    order = models.PositiveSmallIntegerField(verbose_name='Orden', default=0)
    permissions = models.ManyToManyField(Permission, blank=True)

    def __str__(self):
        return f'{self.name} [{self.url}]'

    class Meta:
        verbose_name = 'Módulo'
        verbose_name_plural = 'Módulos'
        ordering = ['menu', 'order', 'name']

# =========================
# MANAGER: GroupModulePermissionManager
# =========================
class GroupModulePermissionManager(models.Manager):
    """
    Obtiene los módulos con su respectivo menú del grupo requerido que estén activos
    """
    def get_group_module_permission_active_list(self, group_id):
        return self.select_related('module', 'module__menu').filter(
            group_id=group_id,
            module__is_active=True
        )
# modulos_activos_de_grupo = GroupModulePermission.objects.get_group_module_permission_active_list(group_id)
# El select_related permite optimizar las consultas a la base de datos, hace un join, y une estos tres:
# GrupoModulePermission | module | menu

# autor = Autor.objects.filter(nombre='Gabriel García Márquez')
# En mi caso voy a decir:
# modulos_activos_de_grupo = GroupModulePermission.objects.get_group_module_permission_active_list(group_id = "1", module__is_active=True)

# =========================
# MODELO: GroupModulePermission
# =========================
"""
Modelo GroupModulePermission: Asocia grupos con módulos y define qué permisos
tiene cada grupo sobre cada módulo específico.

Ejemplos:
1. Usuarios - Sesiones: permisos [view_session, add_session, change_session]
2. Administradores - Ejercicios: permisos [view_exercise, add_exercise, change_exercise]
3. Supervisores - Alertas: permisos [view_alert, add_alert, change_alert]
"""
class GroupModulePermission(models.Model):
    # La relación del campo group indica que un grupo puede tener múltiples permisos sobre diferentes módulos.
    group = models.ForeignKey(Group, on_delete=models.PROTECT, verbose_name='Grupo', related_name='module_permissions')
    module = models.ForeignKey('security.Module', on_delete=models.PROTECT, verbose_name='Módulo', related_name='group_permissions')
    permissions = models.ManyToManyField(Permission, verbose_name='Permisos')
    # Manager personalizado (conserva toda la funcionalidad del manager por defecto)
    objects = GroupModulePermissionManager()

    def __str__(self):
        return f"{self.module.name} - {self.group.name}"

    class Meta:
        verbose_name = 'Grupo módulo permiso'
        verbose_name_plural = 'Grupos módulos permisos'
        ordering = ['group', 'module']
        constraints = [
            UniqueConstraint(fields=['group', 'module'], name='unique_group_module')
        ]

# =========================
# MANAGER: UserManager
# =========================
class UserManager(BaseUserManager):
    """
    Manager personalizado para el modelo User que usa email como identificador principal
    """
    def create_user(self, email, first_name='', last_name='', password=None, **extra_fields):
        """
        Crea y guarda un usuario regular con email, first_name, last_name y password.
        """
        if not email:
            raise ValueError('El email es obligatorio')
        
        email = self.normalize_email(email)
        
        # Generar username si no se proporciona
        if not extra_fields.get('username'):
            base_username = email.split('@')[0]
            # Verificar si el username ya existe y generar uno único
            counter = 0
            username = base_username
            while self.filter(username=username).exists():
                counter += 1
                username = f"{base_username}{counter}"
            extra_fields['username'] = username
        
        user = self.model(
            email=email,
            first_name=first_name,
            last_name=last_name,
            **extra_fields
        )
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, first_name='', last_name='', password=None, **extra_fields):
        """
        Crea y guarda un superusuario con email, first_name, last_name y password.
        """
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('El superusuario debe tener is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('El superusuario debe tener is_superuser=True.')

        return self.create_user(email, first_name, last_name, password, **extra_fields)

# =========================
# MODELO: User
# =========================
"""
Modelo User: Extiende el usuario estándar de Django para añadir campos personalizados.
Utiliza email como identificador principal para login en lugar del username.

Ejemplos:
1. admin (email: admin@visionpulse.com) - Administrador del sistema
2. jperez (email: jperez@empresa.com) - Usuario regular con monitoreo activo
3. mgarcia (email: mgarcia@empresa.com) - Usuario premium con configuraciones avanzadas
"""
class User(AbstractUser, PermissionsMixin):
    # === CONFIGURACIONES DE MONITOREO VISUAL ===
    # Frecuencia de monitoreo
    monitoring_frequency = models.PositiveIntegerField(
        default=30, 
        validators=[MinValueValidator(10), MaxValueValidator(300)],
        help_text="Frecuencia de análisis visual en segundos"
    )
    # Alertas de descanso
    break_reminder_interval = models.PositiveIntegerField(
        default=20, 
        validators=[MinValueValidator(5), MaxValueValidator(120)],
        help_text="Intervalo para recordatorios de descanso en minutos"
    )
    auto_pause_on_fatigue = models.BooleanField(
        default=True,
        help_text="Pausar automáticamente cuando se detecte fatiga extrema"
    )
    # Configuración de ejercicios
    exercise_difficulty = models.CharField(
        max_length=20,
        choices=[
            ('easy', 'Fácil'),
            ('moderate', 'Moderado'),
            ('advanced', 'Avanzado'),
        ],
        default='moderate'
    )
    auto_suggest_exercises = models.BooleanField(
        default=True,
        help_text="Sugerir ejercicios automáticamente basado en fatiga detectada"
    )
    # Notificaciones
    visual_fatigue_alerts = models.BooleanField(default=True)
    break_reminders = models.BooleanField(default=True)
    daily_reports = models.BooleanField(default=True)
    """
    Modelo User personalizado para VisionPulse: Combina funcionalidades de administración
    del sistema con características específicas para monitoreo de salud visual.
    """
    
    image = models.ImageField(
        verbose_name='Imagen de perfil',
        upload_to='security/users/',
        max_length=1024,
        blank=True,
        null=True
    )
    email = models.EmailField('Email', unique=True)
    city = models.CharField('Ciudad', max_length=200, blank=True, null=True)
    country = models.CharField('País', max_length=100, blank=True, null=True)
    phone = models.CharField('Teléfono', max_length=50, blank=True, null=True)
    # === CAMPOS ADICIONALES PARA VISIONPULSE ===
    user_uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    username = models.CharField(
        max_length=150,
        unique=True,
        blank=False,
        null=False,
        help_text="Nombre de usuario único. Obligatorio."
    )
    first_name = models.CharField('Nombres', max_length=150)
    last_name = models.CharField('Apellidos', max_length=150)
    is_verified = models.BooleanField(default=False, help_text="¿Correo verificado? True si viene de OAuth.")
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    last_activity = models.DateTimeField(auto_now=True)
    # password, date_joined, last_login: gestionados por Django
    profile_completed = models.BooleanField(default=False, help_text="¿Completó el onboarding?")

    # =========================
    # CAMPOS OPCIONALES (ONBOARDING / PERFIL)
    # =========================
    USER_TYPES = (
        ('office_worker', 'Trabajador de Oficina'),
        ('programmer', 'Programador'),
        ('designer', 'Diseñador'),
        ('student', 'Estudiante'),
        ('gamer', 'Gamer'),
        ('freelancer', 'Freelancer'),
        ('other', 'Otro'),
    )
    WORK_ENVIRONMENT = (
        ('office', 'Oficina'),
        ('home', 'Casa'),
        ('hybrid', 'Híbrido'),
        ('coworking', 'Coworking'),
        ('other', 'Otro'),
    )
    SCREEN_SIZE = (
        ('small', 'Pequeña (< 15")'),
        ('medium', 'Mediana (15" - 24")'),
        ('large', 'Grande (24" - 32")'),
        ('ultrawide', 'Ultra ancha (> 32")'),
        ('multiple', 'Múltiples pantallas'),
    )
    bio = models.TextField(max_length=500, blank=True, help_text="Breve descripción sobre ti")
    birth_date = models.DateField(null=True, blank=True)
    user_type = models.CharField(max_length=20, choices=USER_TYPES, default='office_worker', blank=True)
    work_environment = models.CharField(max_length=20, choices=WORK_ENVIRONMENT, default='office', blank=True)
    company = models.CharField(max_length=200, blank=True, help_text="Nombre de tu empresa u organización")
    job_title = models.CharField(max_length=200, blank=True, help_text="Tu puesto o rol profesional")
    screen_size = models.CharField(max_length=20, choices=SCREEN_SIZE, default='medium', blank=True)
    preferred_work_time = models.CharField(
        max_length=20,
        choices=[
            ('morning', 'Mañana'),
            ('afternoon', 'Tarde'),
            ('evening', 'Noche'),
            ('late_night', 'Madrugada'),
        ],
        default='morning',
        blank=True,
        help_text="Horario donde más trabajas frente a la pantalla"
    )
    # === ESTADÍSTICAS DE SALUD VISUAL ===
    total_monitoring_time = models.PositiveIntegerField(default=0, help_text="Tiempo total monitoreado en minutos", blank=True)
    total_sessions = models.PositiveIntegerField(default=0, help_text="Número total de sesiones de monitoreo", blank=True)
    current_streak = models.PositiveIntegerField(default=0, help_text="Días consecutivos usando la aplicación", blank=True)
    longest_streak = models.PositiveIntegerField(default=0, blank=True)
    last_streak_update = models.DateField(null=True, blank=True)
    exercises_completed = models.PositiveIntegerField(default=0, help_text="Ejercicios oculares completados", blank=True)
    breaks_taken = models.PositiveIntegerField(default=0, help_text="Descansos tomados por alertas", blank=True)
    fatigue_episodes = models.PositiveIntegerField(default=0, help_text="Episodios de fatiga detectados", blank=True)
    timezone_field = models.CharField(max_length=50, default='America/Guayaquil', blank=True)
    language = models.CharField(max_length=10, default='es', blank=True)
    notifications_enabled = models.BooleanField(default=True)
    email_notifications = models.BooleanField(default=True)
    is_premium = models.BooleanField(default=False)
    premium_until = models.DateTimeField(null=True, blank=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["first_name", "last_name"]  # username se autogenera si no se provee

    # Manager personalizado
    objects = UserManager()

    class Meta:
        verbose_name = "Usuario"
        verbose_name_plural = "Usuarios"
        permissions = (
            ("change_userprofile", "Cambiar perfil de Usuario"),
            ("change_userpassword", "Cambiar contraseña de Usuario"),
        )

    def __str__(self):
        # Evita recursión infinita y errores si get_full_name no es seguro
        try:
            full_name = f"{self.first_name} {self.last_name}".strip()
            if not full_name or full_name == '':
                full_name = self.username or self.email or str(self.pk)
        except Exception:
            full_name = self.username or self.email or str(self.pk)
        return f"{self.email} - {full_name}"

    def save(self, *args, **kwargs):
        # Autogenera username si no se provee (usa la parte antes de la @ del email)
        if not self.username and self.email:
            base_username = self.email.split('@')[0]
            similar = type(self).objects.filter(username__startswith=base_username).exclude(pk=self.pk).count()
            self.username = base_username if similar == 0 else f"{base_username}{similar+1}"
        super().save(*args, **kwargs)

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}".strip() or self.username

    def get_groups(self):
        return self.groups.all()

    def get_short_name(self):
        return self.username

    def get_image(self):
        if self.image:
            return self.image.url
        else:
            return '/static/img/usuario_anonimo.png'
    
    # === MÉTODOS PARA VISIONPULSE ===
    
    def get_health_score(self):
        """Calcula un puntaje de salud visual basado en estadísticas"""
        if self.total_sessions == 0:
            return 0
            
        # Factor positivo: ejercicios completados y descansos tomados
        positive_factor = (self.exercises_completed * 2) + (self.breaks_taken * 3)
        
        # Factor negativo: episodios de fatiga
        negative_factor = self.fatigue_episodes * 5
        
        # Cálculo base sobre total de sesiones
        base_score = max(0, (positive_factor - negative_factor) / self.total_sessions * 100)
        return min(100, base_score)
    
    def add_monitoring_time(self, minutes):
        """Añade tiempo de monitoreo al usuario"""
        self.total_monitoring_time += minutes
        self.save()
    
    def record_exercise_completed(self):
        """Registra un ejercicio ocular completado"""
        self.exercises_completed += 1
        self.save()
    
    def record_break_taken(self):
        """Registra un descanso tomado por alerta"""
        self.breaks_taken += 1
        self.save()
    
    def record_fatigue_episode(self):
        """Registra un episodio de fatiga detectado"""
        self.fatigue_episodes += 1
        self.save()
    
    def update_streak(self):
        """Actualiza la racha de días consecutivos"""
        now = timezone.now().date()
        if self.last_streak_update:
            if self.last_streak_update == now:
                return  # Ya se actualizó hoy
            elif self.last_streak_update == now - timezone.timedelta(days=1):
                self.current_streak += 1
            else:
                self.current_streak = 1
        else:
            self.current_streak = 1
            
        if self.current_streak > self.longest_streak:
            self.longest_streak = self.current_streak
            
        self.last_streak_update = now
        self.save()
    
    def is_premium_active(self):
        """Verifica si el usuario tiene premium activo"""
        if not self.is_premium:
            return False
        if self.premium_until and self.premium_until < timezone.now():
            self.is_premium = False
            self.save()
            return False
        return True

class AuditUser(models.Model):
    usuario = models.ForeignKey(User, verbose_name='Usuario',on_delete=models.PROTECT)
    tabla = models.CharField(max_length=100, verbose_name='Tabla')
    registroid = models.IntegerField(verbose_name='Registro Id')
    accion = models.CharField(choices=AccionChoices, max_length=15, verbose_name='Accion')
    fecha = models.DateField(verbose_name='Fecha')
    hora = models.TimeField(verbose_name='Hora')
    estacion = models.CharField(max_length=100, verbose_name='Estacion')

    def __str__(self):
        return "{} - {} [{}]".format(self.usuario.username, self.tabla, self.accion)

    class Meta:
        verbose_name = 'Auditoria Usuario '
        verbose_name_plural = 'Auditorias Usuarios'
        ordering = ('-fecha', 'hora')


# =========================
# MODELOS ESPECÍFICOS PARA VISIONPULSE
# =========================

# Los modelos de MonitoringSession, FatigueAlert, EyeExercise y ExerciseCompletion
# se han movido a sus respectivas aplicaciones: monitoring, exercises


class NotificationPreference(models.Model):
    """
    Preferencias de notificación por canal.
    """
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


class APIKey(models.Model):
    """
    Si se exponen APIs o integraciones, claves para servicio.
    """
    name = models.CharField(max_length=120)
    key = models.CharField(max_length=255, unique=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Clave API'
        verbose_name_plural = 'Claves API'

    def __str__(self):
        return f"{self.name} - {'active' if self.active else 'inactive'}"


class UserProfile(models.Model):
    """
    Perfil extendido del usuario para VisionPulse.
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    full_name = models.CharField("Nombre completo", max_length=200, blank=True)
    timezone = models.CharField("Zona horaria", max_length=50, default='UTC')
    locale = models.CharField("Idioma/Localización", max_length=10, default='es')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Perfil de usuario"
        verbose_name_plural = "Perfiles de usuario"

    def __str__(self):
        return f"{self.user.username} - perfil"


class CameraDevice(models.Model):
    """
    Dispositivos de cámara registrados por usuario.
    device_id puede venir del front (MediaDeviceInfo.label / deviceId) o un identificador local.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='camera_devices')
    name = models.CharField(max_length=120)              # ej. "Webcam integrada"
    device_id = models.CharField(max_length=300)         # identificador desde navegador (si aplica)
    is_default = models.BooleanField(default=False)
    last_used = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'device_id')
        indexes = [
            models.Index(fields=['user', 'is_default']),
        ]
        ordering = ['-is_default', 'name']
        verbose_name = 'Dispositivo de Cámara'
        verbose_name_plural = 'Dispositivos de Cámara'

    def __str__(self):
        return f"{self.name} ({self.user.username})"


class UserSettings(models.Model):
    """
    Ajustes personales del usuario para VisionPulse. Validaciones aplicadas para rangos seguros.
    """
    NOTIF_CHOICES = [
        ('visual', 'Visual'),
        ('sound', 'Sonora'),
        ('both', 'Visual y Sonora'),
        ('none', 'Ninguna'),
    ]
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='vision_settings')
    
    # === CONFIGURACIONES DE DETECCIÓN OCULAR ===
    ear_threshold = models.FloatField(
        "Umbral EAR",
        default=0.20,
        validators=[MinValueValidator(0.05), MaxValueValidator(0.40)],
        help_text="Valor recomendado entre 0.08 y 0.25, por defecto 0.20"
    )
    blink_window_frames = models.PositiveSmallIntegerField(
        "Ventana confirmación (frames)",
        default=3,
        validators=[MinValueValidator(1), MaxValueValidator(10)]
    )
    sampling_interval_seconds = models.PositiveIntegerField(
        "Intervalo muestreo (s)",
        default=5,
        validators=[MinValueValidator(1), MaxValueValidator(60)]
    )
    rest_interval_minutes = models.PositiveIntegerField(
        "Intervalo de descanso (min)",
        default=20,
        validators=[MinValueValidator(1), MaxValueValidator(240)]
    )
    
    # === CONFIGURACIONES DE CÁMARA Y DETECCIÓN ===
    camera_enabled = models.BooleanField(default=True)
    face_detection_sensitivity = models.FloatField(
        default=0.7,
        validators=[MinValueValidator(0.1), MaxValueValidator(1.0)],
        help_text="Sensibilidad de detección facial (0.1-1.0)"
    )
    
    # === UMBRALES DE ALERTA ===
    fatigue_threshold = models.FloatField(
        default=0.7,
        validators=[MinValueValidator(0.1), MaxValueValidator(1.0)],
        help_text="Umbral para alertas de fatiga (0.1-1.0)"
    )
    blink_rate_threshold = models.PositiveIntegerField(
        default=15,
        validators=[MinValueValidator(5), MaxValueValidator(30)],
        help_text="Parpadeos mínimos por minuto"
    )
    
    # === CONFIGURACIONES DE NOTIFICACIÓN ===
    notification_mode = models.CharField(max_length=10, choices=NOTIF_CHOICES, default='both')
    notify_inactive_tab = models.BooleanField(default=True)
    
    # === CONFIGURACIONES DE INTERFAZ ===
    dark_mode = models.BooleanField(default=False)
    sound_alerts = models.BooleanField(default=True)
    alert_volume = models.FloatField(
        default=0.5,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)]
    )
    
    # === CONFIGURACIONES DE PRIVACIDAD ===
    data_collection_consent = models.BooleanField(default=False)
    anonymous_analytics = models.BooleanField(default=True)
    
    # === TIMESTAMPS ===
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Ajustes de usuario"
        verbose_name_plural = "Ajustes de usuarios"

    def clean(self):
        from django.core.exceptions import ValidationError
        # asegurar consistencia de valores
        if not (0.05 <= self.ear_threshold <= 0.40):
            raise ValidationError("ear_threshold fuera de rango permitido (0.05 - 0.40).")

    def __str__(self):
        return f"Ajustes ({self.user.username})"


class ConsentRecord(models.Model):
    """
    Registro de consentimiento del usuario para activar la cámara.
    Necesario para auditoría y cumplimiento de privacidad.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='consents')
    given = models.BooleanField(default=False)
    timestamp = models.DateTimeField(default=timezone.now)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=512, blank=True)
    policy_version = models.CharField(max_length=50, default='v1')

    class Meta:
        indexes = [
            models.Index(fields=['user', 'timestamp']),
        ]
        ordering = ['-timestamp']
        verbose_name = 'Registro de Consentimiento'
        verbose_name_plural = 'Registros de Consentimiento'

    def __str__(self):
        return f"Consent {self.user.username}={self.given} @ {self.timestamp:%Y-%m-%d %H:%M}"


