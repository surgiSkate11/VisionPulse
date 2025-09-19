from django.db import models
from django.contrib.auth.models import AbstractUser, Group, Permission, PermissionsMixin
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

# Importar el modelo de usuario personalizado de Studer
# (mantenemos el sistema de menús y módulos existente)

# =========================
# MODELO: Menu
# =========================
"""
Modelo Menu: Representa las categorías principales de navegación del sistema.
Cada menú agrupa varios módulos relacionados funcionalmente.

Ejemplos:
1. Ventas (icon: bi bi-cart, order: 1) - Agrupa módulos de clientes, facturación, cotizaciones
2. Inventario (icon: bi bi-box, order: 2) - Agrupa módulos de productos, stock, transferencias
3. Finanzas (icon: bi bi-cash-coin, order: 3) - Agrupa módulos financieros
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
1. Clientes (url: clientes/, menu: Ventas) - Gestión de clientes
2. Facturación (url: facturacion/, menu: Ventas) - Emisión de facturas
3. Productos (url: productos/, menu: Inventario) - Catálogo de productos
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
1. Vendedores - Clientes: permisos [view_client, add_client, change_client]
2. Contadores - Facturas: permisos [view_invoice, add_invoice, change_invoice]
3. Bodegueros - Stock: permisos [view_stock, add_stock, change_stock]
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
# MODELO: User
# =========================
"""
Modelo User: Extiende el usuario estándar de Django para añadir campos personalizados.
Utiliza email como identificador principal para login en lugar del username.

Ejemplos:
1. admin (email: admin@empresa.com) - Administrador del sistema
2. jperez (email: jperez@empresa.com) - Usuario con roles de Vendedor y Contador
3. mgarcia (email: mgarcia@empresa.com) - Usuario con roles de Contador y Auditor
"""
class User(AbstractUser, PermissionsMixin):
    # === PREFERENCIAS Y CONFIGURACIÓN CENTRALIZADAS ===
    # Pomodoro y estudio
    default_pomodoro_duration = models.PositiveIntegerField(default=25, validators=[MinValueValidator(5), MaxValueValidator(60)])
    default_break_duration = models.PositiveIntegerField(default=5, validators=[MinValueValidator(1), MaxValueValidator(30)])
    auto_start_breaks = models.BooleanField(default=False)
    # UI
    compact_view = models.BooleanField(default=False)
    show_motivational_quotes = models.BooleanField(default=True)
    # IA
    ai_assistance_level = models.CharField(
        max_length=20,
        choices=[
            ('minimal', 'Mínima'),
            ('moderate', 'Moderada'),
            ('full', 'Completa'),
        ],
        default='moderate'
    )
    auto_generate_summaries = models.BooleanField(default=True)
    # Notificaciones
    study_reminders = models.BooleanField(default=True)
    task_deadlines = models.BooleanField(default=True)
    achievement_notifications = models.BooleanField(default=True)
    """
    Modelo User personalizado para Studer: Combina funcionalidades de administración
    del sistema con características específicas de la plataforma educativa.
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
    # === NUEVOS CAMPOS PARA STUDER ===
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
        ('student', 'Estudiante'),
        ('autodidact', 'Autodidacta'),
        ('professional', 'Profesional'),
        ('admin', 'Administrador'),
    )
    STUDY_LEVELS = (
        ('high_school', 'Bachillerato'),
        ('university', 'Universidad'),
        ('technical', 'Técnico'),
        ('postgraduate', 'Postgrado'),
        ('self_learning', 'Autoaprendizaje'),
    )
    LEARNING_STYLES = (
        ('visual', 'Visual'),
        ('auditory', 'Auditivo'),
        ('kinesthetic', 'Kinestésico'),
        ('reading_writing', 'Lectoescritor'),
        ('mixed', 'Mixto'),
    )
    bio = models.TextField(max_length=500, blank=True, help_text="Breve descripción sobre ti")
    birth_date = models.DateField(null=True, blank=True)
    user_type = models.CharField(max_length=20, choices=USER_TYPES, default='student', blank=True)
    study_level = models.CharField(max_length=20, choices=STUDY_LEVELS, default='university', blank=True)
    institution = models.CharField(max_length=200, blank=True, help_text="Nombre de tu institución educativa")
    major = models.CharField(max_length=200, blank=True, help_text="Carrera o área de estudio")
    learning_style = models.CharField(max_length=20, choices=LEARNING_STYLES, default='mixed', blank=True)
    preferred_study_time = models.CharField(
        max_length=20,
        choices=[
            ('morning', 'Mañana'),
            ('afternoon', 'Tarde'),
            ('evening', 'Noche'),
            ('late_night', 'Madrugada'),
        ],
        default='morning',
        blank=True
    )
    total_xp = models.PositiveIntegerField(default=0, blank=True)
    current_level = models.PositiveIntegerField(default=1, blank=True)
    current_streak = models.PositiveIntegerField(default=0, help_text="Días consecutivos de actividad", blank=True)
    longest_streak = models.PositiveIntegerField(default=0, blank=True)
    last_streak_update = models.DateField(null=True, blank=True)
    total_study_time = models.PositiveIntegerField(default=0, help_text="Tiempo total de estudio en minutos", blank=True)
    tasks_completed = models.PositiveIntegerField(default=0, blank=True)
    notes_created = models.PositiveIntegerField(default=0, blank=True)
    timezone_field = models.CharField(max_length=50, default='America/Guayaquil', blank=True)
    language = models.CharField(max_length=10, default='es', blank=True)
    notifications_enabled = models.BooleanField(default=True)
    email_notifications = models.BooleanField(default=True)
    is_premium = models.BooleanField(default=False)
    premium_until = models.DateTimeField(null=True, blank=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["first_name", "last_name"]  # username se autogenera si no se provee

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
    last_streak_update = models.DateField(null=True, blank=True)
    total_study_time = models.PositiveIntegerField(default=0, help_text="Tiempo total de estudio en minutos", blank=True)
    tasks_completed = models.PositiveIntegerField(default=0, blank=True)
    notes_created = models.PositiveIntegerField(default=0, blank=True)
    timezone_field = models.CharField(max_length=50, default='America/Guayaquil', blank=True)
    language = models.CharField(max_length=10, default='es', blank=True)
    notifications_enabled = models.BooleanField(default=True)
    email_notifications = models.BooleanField(default=True)
    is_premium = models.BooleanField(default=False)
    premium_until = models.DateTimeField(null=True, blank=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["first_name", "last_name"]  # username se autogenera si no se provee

    class Meta:
        verbose_name = "Usuario"
        verbose_name_plural = "Usuarios"
        permissions = (
            ("change_userprofile", "Cambiar perfil de Usuario"),
            ("change_userpassword", "Cambiar contraseña de Usuario"),
        )

    # (Elimina duplicado de __str__ y save)

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
    
    # === NUEVOS MÉTODOS PARA STUDER ===
    
    def get_level_progress(self):
        """Calcula el progreso hacia el siguiente nivel"""
        from django.conf import settings
        levels = settings.STUDER_SETTINGS['GAMIFICATION']['LEVELS']
        
        current_level_xp = levels.get(self.current_level, 0)
        next_level_xp = levels.get(self.current_level + 1, float('inf'))
        
        if next_level_xp == float('inf'):
            return 100  # Nivel máximo alcanzado
            
        progress = ((self.total_xp - current_level_xp) / (next_level_xp - current_level_xp)) * 100
        return min(100, max(0, progress))
    
    def add_xp(self, amount):
        """Añade XP al usuario y actualiza el nivel si es necesario"""
        self.total_xp += amount
        self._update_level()
        self.save()
    
    def _update_level(self):
        """Actualiza el nivel basado en el XP total"""
        from django.conf import settings
        levels = settings.STUDER_SETTINGS['GAMIFICATION']['LEVELS']
        
        for level, required_xp in sorted(levels.items(), reverse=True):
            if self.total_xp >= required_xp:
                self.current_level = level
                break
    
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
# MODELOS ADICIONALES PARA STUDER
# =========================


