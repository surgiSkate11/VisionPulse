from django.conf import settings
from django.db import models
from django.utils.text import slugify
from django.utils import timezone
from django.core.validators import MinValueValidator


def exercise_video_upload_to(instance, filename):
    return f"exercises/videos/{instance.slug}/{filename}"


class Exercise(models.Model):
    """
    Catálogo de ejercicios oculares.
    """
    EXERCISE_TYPES = [
        ('parpadeo', 'Ejercicio de Parpadeo'),
        ('enfoque', 'Ejercicio de Enfoque'),
        ('movimiento', 'Ejercicio de Movimiento'),
        ('relajacion', 'Ejercicio de Relajación'),
    ]
    DIFFICULTY = [
        ('easy', 'Fácil'),
        ('med', 'Media'),
        ('hard', 'Difícil')
    ]

    title = models.CharField('Título', max_length=200)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    description = models.TextField('Descripción', blank=True, default='')
    type = models.CharField('Tipo', max_length=50, choices=EXERCISE_TYPES, default='movimiento')
    duration_minutes = models.PositiveIntegerField('Duración (minutos)', default=1, 
        help_text='Duración estimada del ejercicio en minutos')
    difficulty = models.CharField('Dificultad', max_length=10, choices=DIFFICULTY, default='easy')
    video = models.FileField('Video', upload_to=exercise_video_upload_to, null=True, blank=True)
    video_link = models.URLField('Video URL', blank=True, null=True)
    instruction_steps = models.TextField('Instrucciones', default='', 
        help_text='Instrucciones paso a paso del ejercicio')
    icon = models.ImageField('Icono', upload_to='exercises/icons/', null=True, blank=True)
    active = models.BooleanField('Activo', default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['title']
        verbose_name = 'Ejercicio'
        verbose_name_plural = 'Ejercicios'

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)[:220]
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title


class ExerciseSession(models.Model):
    """
    Registro de que un usuario realizó un ejercicio.
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='exercise_sessions')
    exercise = models.ForeignKey(
        Exercise, 
        on_delete=models.SET_NULL,  # Mantenemos SET_NULL para preservar el historial
        null=True,  # Permitimos null para manejar ejercicios eliminados
        related_name='sessions',
        verbose_name='Ejercicio'
    )
    started_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(null=True, blank=True)
    completed = models.BooleanField('Completado', default=False)
    rating = models.PositiveSmallIntegerField('Calificación', choices=[(i, i) for i in range(1, 6)], null=True, blank=True)
    feedback = models.TextField('Retroalimentación', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-started_at']
        verbose_name = 'Sesión de Ejercicio'
        verbose_name_plural = 'Sesiones de Ejercicios'
        indexes = [
            models.Index(fields=['user', 'started_at']),
        ]

    def mark_completed(self):
        if not self.completed:
            self.completed = True
            self.completed_at = timezone.now()
            self.save(update_fields=['completed', 'completed_at'])

    def duration_minutes(self):
        if self.completed_at:
            return int((self.completed_at - self.started_at).total_seconds() / 60)
        return None

    def __str__(self):
        exercise_name = self.exercise.title if self.exercise else "Ejercicio Eliminado"
        return f"{self.user.username} - {exercise_name} @ {self.started_at:%Y-%m-%d %H:%M}"
