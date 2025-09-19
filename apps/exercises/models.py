from django.conf import settings
from django.db import models
from django.utils.text import slugify
from django.utils import timezone
from django.core.validators import MinValueValidator


def exercise_video_upload_to(instance, filename):
    # ajustar según DEFAULT_FILE_STORAGE (S3/local)
    return f"exercises/videos/{instance.slug}/{filename}"


class Exercise(models.Model):
    """
    Catálogo de ejercicios oculares.
    """
    DIFFICULTY = [('easy', 'Fácil'), ('med', 'Media'), ('hard', 'Difícil')]

    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    description = models.TextField(blank=True)
    duration_seconds = models.PositiveIntegerField(default=20, validators=[MinValueValidator(1)])
    difficulty = models.CharField(max_length=10, choices=DIFFICULTY, default='easy')
    video = models.FileField(upload_to=exercise_video_upload_to, null=True, blank=True)
    icon = models.ImageField(upload_to='exercises/icons/', null=True, blank=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['title']
        verbose_name = 'Ejercicio Ocular'
        verbose_name_plural = 'Ejercicios Oculares'

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)[:220]
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title


class ExerciseStep(models.Model):
    """
    Pasos individuales de un ejercicio.
    """
    exercise = models.ForeignKey(Exercise, on_delete=models.CASCADE, related_name='steps')
    order = models.PositiveSmallIntegerField()
    instruction = models.CharField(max_length=400)
    duration_seconds = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        unique_together = ('exercise', 'order')
        ordering = ['order']
        verbose_name = 'Paso de Ejercicio'
        verbose_name_plural = 'Pasos de Ejercicio'

    def __str__(self):
        return f"{self.exercise.title} - paso {self.order}"


class ExerciseSession(models.Model):
    """
    Registro de que un usuario realizó un ejercicio.
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='exercise_sessions')
    exercise = models.ForeignKey(Exercise, on_delete=models.SET_NULL, null=True)
    started_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(null=True, blank=True)
    completed = models.BooleanField(default=False)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-started_at']
        indexes = [
            models.Index(fields=['user', 'started_at']),
        ]
        verbose_name = 'Sesión de Ejercicio'
        verbose_name_plural = 'Sesiones de Ejercicio'

    def mark_completed(self):
        if not self.completed:
            self.completed = True
            self.completed_at = timezone.now()
            self.save(update_fields=['completed', 'completed_at'])

    def duration_seconds(self):
        if self.completed_at:
            return int((self.completed_at - self.started_at).total_seconds())
        return None

    def __str__(self):
        return f"{self.user.username} - {self.exercise} @ {self.started_at:%Y-%m-%d %H:%M}"
