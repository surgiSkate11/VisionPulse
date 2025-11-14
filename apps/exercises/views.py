# apps/exercises/views.py
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView
from django.http import JsonResponse
from django.conf import settings
from django.views.decorators.http import require_http_methods
from django.utils import timezone
import json
from apps.security.components.sidebar_menu_mixin import SidebarMenuMixin
from .models import Exercise, ExerciseSession

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
    
    # Serializar pasos incluyendo la URL del video si existe (tolerante a archivos faltantes)
    steps_data = []
    for step in exercise.steps.order_by('step_order'):
        video_url = None
        if getattr(step, 'video_clip', None) and step.video_clip:
            try:
                # .url puede lanzar si el archivo ya no existe físicamente
                video_url = step.video_clip.url
            except Exception:
                # Fallback: construir la URL a partir de MEDIA_URL + nombre si existe nombre
                try:
                    name = getattr(step.video_clip, 'name', None)
                    if name:
                        base = settings.MEDIA_URL.rstrip('/')
                        name_str = str(name).lstrip('/')
                        video_url = f"{base}/{name_str}"
                except Exception:
                    video_url = None

        steps_data.append({
            'step_order': step.step_order,
            'instruction': step.instruction,
            'duration_seconds': step.duration_seconds,
            'video_url': video_url,
        })

    data = {
        'id': exercise.id,
        'title': exercise.title,
        'total_duration': exercise.total_duration_seconds,
        'steps': steps_data,
    }
    return JsonResponse(data)


@login_required
@require_http_methods(["POST"])
def start_exercise_session(request, exercise_id):
    """
    Inicia una nueva sesión de ejercicio para el usuario.
    Solo se crea una sesión al comenzar el ejercicio.
    """
    try:
        exercise = get_object_or_404(Exercise, pk=exercise_id, is_active=True)
        
        # Crear una nueva sesión
        session = ExerciseSession.objects.create(
            user=request.user,
            exercise=exercise,
            started_at=timezone.now()
        )
        
        return JsonResponse({
            'success': True,
            'session_id': session.id,
            'message': 'Sesión iniciada correctamente'
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)


@login_required
@require_http_methods(["POST"])
def complete_exercise_session(request, session_id):
    """
    Marca una sesión de ejercicio como completada y/o actualiza su calificación.
    Puede ser llamado múltiples veces: primero para completar, luego para calificar.
    """
    try:
        data = json.loads(request.body)
        
        # Obtener la sesión del usuario
        session = get_object_or_404(
            ExerciseSession, 
            id=session_id, 
            user=request.user
        )
        
        # Marcar como completada si aún no lo está
        if not session.completed:
            session.mark_completed()
        
        # Actualizar calificación si se proporciona (puede ser después de completar)
        if 'rating' in data and data['rating']:
            session.rating = data['rating']
            session.save()
            message = 'Calificación guardada correctamente'
        else:
            message = 'Ejercicio completado correctamente'
        
        return JsonResponse({
            'success': True,
            'message': message,
            'duration_minutes': session.duration_minutes(),
            'completion_percentage': session.completion_percentage(),
            'rating': session.rating
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)


@login_required
@require_http_methods(["POST"])
def cancel_exercise_session(request, session_id):
    """
    Cancela una sesión de ejercicio sin marcarla como completada.
    Útil cuando el usuario abandona el ejercicio antes de terminarlo.
    """
    try:
        # Intentar obtener la sesión del usuario
        try:
            session = ExerciseSession.objects.get(
                id=session_id, 
                user=request.user
            )
        except ExerciseSession.DoesNotExist:
            # La sesión ya no existe (puede haberse eliminado o nunca existió)
            return JsonResponse({
                'success': True,
                'message': 'La sesión ya no existe o ya fue cancelada'
            })
        
        # Si ya estaba completada, no hacer nada
        if session.completed:
            return JsonResponse({
                'success': True,
                'message': 'La sesión ya estaba completada'
            })
        
        # Eliminar la sesión incompleta para no llenar la BD
        session.delete()
        
        return JsonResponse({
            'success': True,
            'message': 'Sesión cancelada correctamente'
        })
        
    except Exception as e:
        # Log del error pero retornar 200 para no bloquear el cierre del modal
        import logging
        logging.error(f"[EXERCISE] Error al cancelar sesión {session_id}: {e}")
        return JsonResponse({
            'success': True,  # Cambiar a True para no bloquear
            'message': 'Error al cancelar pero se permite cerrar el modal',
            'error': str(e)
        })
