from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from ..models import AlertTypeConfig, AlertEvent, get_effective_detection_config
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_protect

@login_required
@require_http_methods(["GET"])
def get_alert_config(request, alert_type):
    """
    Retorna la configuración para un tipo específico de alerta.
    Incluye configuraciones personalizadas del usuario si existen.
    """
    try:
        # Obtener configuración base (solo título, descripción y audio por tipo)
        config = AlertTypeConfig.objects.get(alert_type=alert_type)

        # Config efectiva por usuario (con defaults propios del usuario)
        effective = get_effective_detection_config(request.user)

        # Título localizado del tipo de alerta
        alert_title = dict(AlertEvent.ALERT_TYPES).get(alert_type, 'Alerta')

        # Preferir valores del usuario; no depender de umbrales/tiempos del tipo
        user_config = getattr(request.user, 'monitoring_config', None)
        max_reps = getattr(user_config, 'repeat_max_per_hour', None) if user_config else None

        response = {
            'title': alert_title,
            'message': config.description,
            'defaultVoiceClip': config.default_voice_clip.url if config.default_voice_clip else None,
            'maxRepetitions': max_reps if max_reps is not None else 3,
            'cooldownSeconds': effective.get('alert_cooldown_seconds', 60),
            'autoDismiss': not bool((max_reps if max_reps is not None else 3) > 1),
            'autoDismissDelay': 5000,
            'level': 'medium',  # Por defecto medium, se puede personalizar por tipo
            'hysteresisTimeout': effective.get('hysteresis_timeout_seconds', 30),
            'detectionDelay': effective.get('detection_delay_seconds', 5),
        }

        return JsonResponse(response)
        
    except AlertTypeConfig.DoesNotExist:
        # Configuración por defecto si no existe
        return JsonResponse({
            'maxRepetitions': 3,
            'cooldownSeconds': 10,
            'defaultVoiceClip': None,
            'description': '',
            'autoDismiss': True,
            'autoDismissDelay': 5000,
        })
    except Exception as e:
        return JsonResponse({
            'error': str(e)
        }, status=500)

@login_required
@csrf_protect
@require_http_methods(["POST"])
def cleanup_alerts(request):
    """Limpia todas las alertas pendientes de una sesión"""
    try:
        # Aquí puedes agregar lógica adicional para limpiar alertas según necesites
        return JsonResponse({'status': 'success'})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)