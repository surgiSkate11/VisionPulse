# apps/exercises/models.py
from django.db import models
from django.core.validators import MinValueValidator
from django.conf import settings
from django.utils import timezone

class Exercise(models.Model):
    """
    Representa un ejercicio ocular completo, que es una colección de pasos.
    """
    title = models.CharField('Título', max_length=200)
    description = models.TextField('Descripción', help_text='Una descripción corta para la tarjeta del catálogo.')
    icon_class = models.CharField('Clase del Icono (FontAwesome)', max_length=50, help_text='Ej: "fas fa-eye". El ícono para el catálogo.')
    is_active = models.BooleanField('Está Activo', default=True, help_text='Desmarca esto para ocultar el ejercicio del catálogo.')

    class Meta:
        verbose_name = 'Ejercicio'
        verbose_name_plural = 'Ejercicios'
        ordering = ['title']

    def __str__(self):
        return self.title

    @property
    def total_duration_seconds(self):
        """Calcula la duración total del ejercicio sumando la duración de todos sus pasos."""
        total = self.steps.aggregate(total=models.Sum('duration_seconds'))['total']
        return total or 0

    @property
    def total_duration_minutes(self):
        """Devuelve la duración total en minutos redondeados para mostrar en el catálogo."""
        if self.total_duration_seconds == 0:
            return 0
        return max(1, round(self.total_duration_seconds / 60)) # Muestra al menos 1 minuto si hay pasos

class ExerciseStep(models.Model):
    """
    Representa un paso individual dentro de un ejercicio, con su propia animación y duración.
    """
    exercise = models.ForeignKey(Exercise, on_delete=models.CASCADE, related_name='steps', verbose_name='Ejercicio')
    step_order = models.PositiveIntegerField('Orden del Paso', help_text='El orden en que este paso aparecerá (1, 2, 3...).')
    instruction = models.CharField('Instrucción', max_length=255, help_text='La instrucción que el usuario debe seguir.')
    icon_class = models.CharField('Clase del Icono de Animación (FontAwesome)', max_length=50, help_text='Ej: "fas fa-sync-alt fa-spin". El ícono que se mostrará durante este paso.')
    duration_seconds = models.PositiveIntegerField('Duración del paso (segundos)', validators=[MinValueValidator(1)])

    class Meta:
        verbose_name = 'Paso del Ejercicio'
        verbose_name_plural = 'Pasos del Ejercicio'
        ordering = ['exercise', 'step_order']
        unique_together = ('exercise', 'step_order') # Evita pasos duplicados para un mismo ejercicio

    def __str__(self):
        return f"{self.exercise.title} - Paso {self.step_order}"




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
