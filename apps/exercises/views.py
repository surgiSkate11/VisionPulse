# apps/exercises/views.py
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView
from django.http import JsonResponse
from apps.security.components.sidebar_menu_mixin import SidebarMenuMixin
from .models import Exercise

class ExerciseCatalogView(LoginRequiredMixin, SidebarMenuMixin, ListView):
    """
    Muestra la página con la lista de todos los ejercicios activos.
    """
    model = Exercise
    template_name = 'exercises/catalog.html'
    context_object_name = 'exercises'
    
    def get_queryset(self):
        return Exercise.objects.filter(is_active=True)


@login_required
def exercise_data(request, pk):
    """
    Devuelve los datos de un ejercicio y sus pasos en formato JSON.
    """
    exercise = get_object_or_404(Exercise, pk=pk, is_active=True)
    
    # Serializar pasos incluyendo la URL del video si existe
    steps_data = []
    for step in exercise.steps.order_by('step_order'):
        steps_data.append({
            'step_order': step.step_order,
            'instruction': step.instruction,
            'duration_seconds': step.duration_seconds,
            'video_url': step.video_clip.url if getattr(step, 'video_clip', None) and step.video_clip else None,
        })

    data = {
        'id': exercise.id,
        'title': exercise.title,
        'total_duration': exercise.total_duration_seconds,
        'steps': steps_data,
    }
    return JsonResponse(data)
