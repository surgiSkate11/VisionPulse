# apps/exercises/admin.py
from django.contrib import admin
from .models import Exercise, ExerciseStep, ExerciseSession

class ExerciseStepInline(admin.TabularInline):
    """
    Permite editar los pasos directamente desde la página del ejercicio.
    """
    model = ExerciseStep
    extra = 1
    ordering = ('step_order',)

@admin.register(Exercise)
class ExerciseAdmin(admin.ModelAdmin):
    """
    Configuración del admin para el modelo Exercise.
    """
    list_display = ('title', 'total_duration_minutes', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('title', 'description')
    inlines = [ExerciseStepInline]
    
    def total_duration_minutes(self, obj):
        return f"{obj.total_duration_minutes} min"
    total_duration_minutes.short_description = 'Duración Total'

@admin.register(ExerciseSession)
class ExerciseSessionAdmin(admin.ModelAdmin):
    """
    Configuración del admin para ver el historial de sesiones.
    """
    list_display = ('user', 'exercise', 'started_at', 'completed_at')
    list_filter = ('started_at',)
    search_fields = ('user__username', 'exercise__title')
    readonly_fields = ('user', 'exercise', 'started_at', 'completed_at')

    def has_add_permission(self, request):
        return False
