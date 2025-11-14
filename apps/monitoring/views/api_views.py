"""
API Views - Endpoints de la API para monitoreo
Este módulo contiene todas las vistas de API (JSON responses) para el sistema de monitoreo
"""

from django.http import JsonResponse, StreamingHttpResponse
import logging
import numpy as np
import time
import json

import cv2
from django.http import JsonResponse, StreamingHttpResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils import timezone

from ..models import MonitorSession
from .controller import controller

# Safe serialization helper
def safe_serialize_response(data: dict) -> JsonResponse:
    """
    Serializa una respuesta de forma segura, convirtiendo tipos no serializables.
    """
    def convert_value(obj):
        if obj is None:
            return None
        if isinstance(obj, (np.integer, np.int64, np.int32, np.int16, np.int8)):
            return int(obj)
        if isinstance(obj, (np.floating, np.float64, np.float32, np.float16)):
            return float(obj)
        if isinstance(obj, (np.bool_, bool)):
            return bool(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, (int, float, str, type(None))):
            return obj
        if isinstance(obj, dict):
            return {k: convert_value(v) for k, v in obj.items()}
            from django.http import JsonResponse, StreamingHttpResponse
        if isinstance(obj, (list, tuple)):
            return [convert_value(item) for item in obj]
        try:
            return float(obj)
        except (ValueError, TypeError):
            return str(obj)
    try:
        serializable_data = convert_value(data)
        return JsonResponse(serializable_data, safe=False)
    except Exception as e:
        logging.error(f"[API] Error serializando respuesta: {e}")
        return JsonResponse({
            'status': 'error',
            'message': f'Error de serialización: {str(e)}',
            'original_status': data.get('status', 'unknown')
        }, status=500)


def generate_frames():
    """Generador de frames para el streaming de video"""
    while controller.camera_manager and controller.camera_manager.is_running:
        frame, metrics = controller.camera_manager.get_frame()
        # Si la cámara está pausada o detenida, cortar el stream
        if controller.camera_manager.is_paused or not controller.camera_manager.is_running:
            # Enviar un frame negro y terminar el stream
            import numpy as np
            black_frame = np.zeros((480, 640, 3), dtype=np.uint8)
            _, buffer = cv2.imencode('.jpg', black_frame)
            frame_bytes = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
            break
        if frame is None:
            continue
        # Codificar el frame para streaming
        try:
            _, buffer = cv2.imencode('.jpg', frame)
            frame_bytes = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        except Exception as e:
            print(f"[ERROR] Error al codificar frame: {str(e)}")
            continue


@login_required
def video_feed(request):
    """Stream de video en vivo"""
    return StreamingHttpResponse(
        generate_frames(),
        content_type='multipart/x-mixed-replace; boundary=frame'
    )


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def start_session(request):
    """Inicia una nueva sesión de monitoreo"""
    try:
        logging.info(f"[START] Usuario {request.user.username} intentando iniciar nueva sesión")
        
        # Verificar si hay una sesión activa
        if controller.camera_manager and controller.camera_manager.is_running:
            logging.warning(f"[START] Sesión ya activa para usuario {request.user.username}")
            return JsonResponse({
                'status': 'error',
                'message': 'Ya hay una sesión activa. Detén la sesión actual primero.'
            }, status=400)
        
        # Cerrar sesiones anteriores sin cerrar
        unclosed = MonitorSession.objects.filter(
            user=request.user,
            end_time__isnull=True
        ).update(
            end_time=timezone.now(),
            status='interrupted'
        )
        
        if unclosed > 0:
            logging.info(f"[START] Cerradas {unclosed} sesiones sin terminar")
        
        # Iniciar sesión directamente
        success, error, session = controller.start_session(request.user)
        
        if not success:
            logging.error(f"[START] Error al iniciar sesión: {error}")
            return JsonResponse({
                'status': 'error',
                'message': error or 'Error desconocido al iniciar la sesión'
            }, status=500)
        
        if not session:
            logging.error("[START] Sesión None después de inicio exitoso")
            return JsonResponse({
                'status': 'error',
                'message': 'Error interno: sesión no creada'
            }, status=500)
        
        logging.info(f"[START] Sesión {session.id} iniciada correctamente")
        return JsonResponse({
            'status': 'success',
            'message': 'Monitoreo iniciado correctamente',
            'session_id': session.id,
            'start_time': session.start_time.isoformat()
        })
        
    except Exception as e:
        logging.exception("[START] Error inesperado al iniciar sesión")
        return JsonResponse({
            'status': 'error',
            'message': f'Error inesperado: {str(e)}'
        }, status=500)


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def stop_session(request):
    """Finaliza la sesión actual"""
    success, error, session_summary = controller.end_session()
    if not success:
        return JsonResponse({
            'status': 'error',
            'message': error
        }, status=400)
    # ¡SOLUCIÓN! Usar el serializador seguro
    return safe_serialize_response({
        'status': 'success',
        'message': 'Monitoreo finalizado correctamente',
        'summary': session_summary
    })


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def pause_monitoring(request):
    """Pausa la sesión actual"""
    try:
        # Obtener datos del request para determinar el tipo de pausa
        data = {}
        if request.body:
            try:
                data = json.loads(request.body)
            except json.JSONDecodeError:
                pass
        
        alert_type = data.get('reason', '').lower()
        is_auto_pause = data.get('auto_pause', False)
        
        # Si es auto-pausa por alerta crítica, usar el método específico
        if is_auto_pause:
            if 'driver_absent' in alert_type or 'usuario ausente' in alert_type:
                logging.info("[API] Auto-pausa por driver_absent")
                ok, msg, pause_data = controller.auto_pause_driver_absent()
                if not ok:
                    return JsonResponse({
                        'status': 'error',
                        'message': msg
                    }, status=400)
                return JsonResponse({
                    'status': 'success',
                    'message': 'Monitoreo pausado automáticamente por usuario ausente',
                    'total_blinks': int(pause_data.get('blink_count', 0)),
                    'blink_count': int(pause_data.get('blink_count', 0)),
                    'is_paused': True,
                    'session_id': pause_data.get('session_id'),
                    'paused_by': 'driver_absent'
                })
            elif 'multiple_people' in alert_type or 'múltiples personas' in alert_type:
                logging.info("[API] Auto-pausa por multiple_people")
                ok, msg, pause_data = controller.auto_pause_multiple_people()
                if not ok:
                    return JsonResponse({
                        'status': 'error',
                        'message': msg
                    }, status=400)
                return JsonResponse({
                    'status': 'success',
                    'message': 'Monitoreo pausado automáticamente por múltiples personas',
                    'total_blinks': int(pause_data.get('blink_count', 0)),
                    'blink_count': int(pause_data.get('blink_count', 0)),
                    'is_paused': True,
                    'session_id': pause_data.get('session_id'),
                    'paused_by': 'multiple_people'
                })
        
        # Pausa manual normal
        success, message, data = controller.pause_session()
        if not success:
            return JsonResponse({
                'status': 'error',
                'message': message
            }, status=400)
        response_data = {
            'status': 'success',
            'message': str(message),
            'total_blinks': int(data.get('blink_count', 0)),
            'blink_count': int(data.get('blink_count', 0)),
            'is_paused': bool(data.get('is_paused', True)),
            'session_id': data.get('session_id'),
            'timestamp': str(data.get('timestamp', ''))
        }
        return safe_serialize_response(response_data)
    except Exception as e:
        logging.exception("[API] Error en pause_monitoring")
        return JsonResponse({
            'status': 'error',
            'message': f'Error al pausar: {str(e)}'
        }, status=500)


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def resume_monitoring(request):
    """Reanuda la sesión actual"""
    try:
        # Limpiar flag de pausa por ejercicio si viene explícitamente del frontend
        if hasattr(controller, 'paused_by_exercise') and controller.paused_by_exercise:
            logging.info("[API] Limpiando flag paused_by_exercise (llamada explícita desde frontend)")
            controller.paused_by_exercise = False
            controller._last_checked_exercise_id = None
            controller._paused_by_exercise_timestamp = None
        # Activar una pequeña ventana de gracia para evitar re-pausa inmediata por polling
        try:
            from datetime import timedelta
            controller.exercise_resume_grace_until = timezone.now() + timedelta(seconds=5)
        except Exception:
            controller.exercise_resume_grace_until = None
        
        success, message, data = controller.resume_session()
        if not success:
            return JsonResponse({
                'status': 'error',
                'message': message
            }, status=400)
        response_data = {
            'status': 'success',
            'message': str(message),
            'total_blinks': int(data.get('blink_count', 0)),
            'blink_count': int(data.get('blink_count', 0)),
            'is_paused': bool(data.get('is_paused', False)),
            'session_id': data.get('session_id'),
            'timestamp': str(data.get('timestamp', ''))
        }
        return safe_serialize_response(response_data)
    except Exception as e:
        logging.exception("[API] Error en resume_monitoring")
        return JsonResponse({
            'status': 'error',
            'message': f'Error al reanudar: {str(e)}'
        }, status=500)


@login_required
def session_metrics(request):
    """Retorna las métricas actuales de la sesión"""
    try:
        metrics_data = controller.get_metrics()
        if not isinstance(metrics_data, dict):
            logging.error(f"[API] get_metrics() retornó tipo inválido: {type(metrics_data)}")
            return JsonResponse({
                'status': 'error',
                'message': 'Error interno: formato de métricas inválido',
                'metrics': {},
                'is_paused': False,
                'alerts': []
            }, status=500)
        return safe_serialize_response(metrics_data)
    except Exception as e:
        logging.exception("[API] Error inesperado en session_metrics")
        return JsonResponse({
            'status': 'error',
            'message': f'Error obteniendo métricas: {str(e)}',
            'metrics': {
                'ear': 0.0,
                'focus': 'Error',
                'faces': 0,
                'eyes_detected': False,
                'total_blinks': 0
            },
            'is_paused': False,
            'alerts': []
        }, status=500)


@login_required
def camera_status(request):
    """Verifica el estado de la cámara y devuelve información de diagnóstico"""
    
    try:
        if not controller.camera_manager:
            return safe_serialize_response({
                'camera_running': False,
                'video_initialized': False,
                'video_opened': False,
                'session_active': False,
                'is_paused': False,
                'error_count': 0,
                'can_read_frames': False,
                'message': 'CameraManager no inicializado. Inicia una sesión primero.'
            })

        status = {
            'camera_running': bool(controller.camera_manager.is_running),
            'video_initialized': controller.camera_manager.video is not None,
            'video_opened': bool(controller.camera_manager.video.isOpened() if controller.camera_manager.video else False),
            'session_active': controller.camera_manager.session_id is not None,
            'is_paused': bool(controller.camera_manager.is_paused),
            'error_count': int(controller.camera_manager.error_count),
        }

        try:
            if controller.camera_manager.video:
                frame_test = controller.camera_manager.video.read()[0]
                status['can_read_frames'] = bool(frame_test)
            else:
                status['can_read_frames'] = False
        except Exception as e:
            status['can_read_frames'] = False
            status['read_error'] = str(e)

        return safe_serialize_response({
            'status': 'success',
            'camera_status': status,
            'message': 'Estado de la cámara obtenido correctamente'
        })
    except Exception as e:
        logging.exception("[API] Error en camera_status")
        return JsonResponse({
            'status': 'error',
            'message': f'Error obteniendo estado: {str(e)}'
        }, status=500)


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def snooze_break_reminder(request):
    """Pospone el recordatorio de descanso por X minutos"""
    try:
        data = json.loads(request.body)
        snooze_minutes = data.get('minutes', 5)  # default: 5 minutos
        
        # Ajustar el último recordatorio usando tiempo efectivo de monitoreo
        effective_duration = controller.session_data.get('effective_duration', 0)
        controller.last_break_reminder = effective_duration
        
        return JsonResponse({
            'status': 'success',
            'message': f'Recordatorio pospuesto por {snooze_minutes} minutos',
            'next_reminder_in_seconds': snooze_minutes * 60
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            'status': 'error',
            'message': 'JSON inválido'
        }, status=400)
    except Exception as e:
        logging.error(f"[BREAK] Error al posponer recordatorio: {e}")
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=400)


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def mark_break_taken(request):
    """
    Marca que el usuario aceptó tomar un descanso.
    Comportamiento:
    - Pausa automáticamente el monitoreo
    - Resetea el contador de recordatorios
    - Descarta alertas activas (excepto críticas)
    """
    try:
        if not controller.user_config:
            return JsonResponse({
                'status': 'error',
                'message': 'No hay sesión activa'
            }, status=400)
        
        user = controller.user_config
        
        # 1. Pausar el monitoreo automáticamente
        ok, msg, pause_data = controller.pause_session()
        
        if not ok:
            logging.error(f"[BREAK] Error al pausar monitoreo: {msg}")
            return JsonResponse({
                'status': 'error',
                'message': f'Error al pausar monitoreo: {msg}'
            }, status=400)
        
        # 2. Resetear contador de recordatorios usando tiempo efectivo
        effective_duration = controller.session_data.get('effective_duration', 0)
        controller.last_break_reminder = effective_duration
        
        return JsonResponse({
            'status': 'success',
            'message': 'Descanso iniciado - monitoreo pausado',
            'is_paused': True,
            'blink_count': pause_data.get('blink_count', 0)
        })
        
    except Exception as e:
        logging.error(f"[BREAK] Error al registrar descanso: {e}", exc_info=True)
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=400)


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def alert_complete_exercise(request):
    """
    Marca una alerta como resuelta cuando el usuario completa un ejercicio.
    """
    try:
        data = json.loads(request.body)
        alert_id = data.get('alert_id')
        exercise_session_id = data.get('exercise_session_id')

        if not alert_id:
            return JsonResponse({
                'status': 'error',
                'message': 'alert_id es requerido'
            }, status=400)

        from ..models import AlertEvent
        from apps.exercises.models import ExerciseSession

        # Buscar la alerta
        try:
            alert = AlertEvent.objects.get(id=alert_id, session__user=request.user)
        except AlertEvent.DoesNotExist:
            return JsonResponse({
                'status': 'error',
                'message': 'Alerta no encontrada'
            }, status=404)

        # Marcar como resuelta
        alert.auto_resolved = False
        alert.resolution_method = 'exercise'

        # Si hay una sesión de ejercicio, vincularla
        if exercise_session_id:
            try:
                exercise_session = ExerciseSession.objects.get(
                    id=exercise_session_id,
                    user=request.user
                )
                alert.exercise_session = exercise_session
            except ExerciseSession.DoesNotExist:
                logging.warning(f"[ALERT] Sesión de ejercicio {exercise_session_id} no encontrada")

        alert.save()

        logging.info(f"[ALERT] Alerta {alert_id} resuelta por ejercicio para usuario {request.user.username}")

        return JsonResponse({
            'status': 'success',
            'message': 'Alerta marcada como resuelta',
            'alert_id': alert_id,
            'resolution_method': 'exercise'
        })

    except json.JSONDecodeError:
        return JsonResponse({
            'status': 'error',
            'message': 'JSON inválido'
        }, status=400)
    except Exception as e:
        logging.error(f"[ALERT] Error al completar ejercicio: {e}")
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)
