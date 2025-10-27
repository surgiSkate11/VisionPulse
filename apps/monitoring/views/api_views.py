"""
API Views - Endpoints de la API para monitoreo
Este módulo contiene todas las vistas de API (JSON responses) para el sistema de monitoreo
"""

import logging
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


def generate_frames():
    """Generador de frames para el streaming de video"""
    while controller.camera_manager and controller.camera_manager.is_running:
        frame, metrics = controller.camera_manager.get_frame()
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
        
    return JsonResponse({
        'status': 'success',
        'message': 'Monitoreo finalizado correctamente',
        'summary': session_summary
    })


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def pause_monitoring(request):
    """Pausa la sesión actual"""
    success, message, data = controller.pause_session()
    
    if not success:
        return JsonResponse({
            'status': 'error',
            'message': message
        }, status=400)
    
    response_data = {
        'status': 'success',
        'message': message,
        'total_blinks': data.get('blink_count', 0),  # Garantizar ambos campos
        'blink_count': data.get('blink_count', 0),   # Para retrocompatibilidad
        'is_paused': data.get('is_paused', True),    # True porque estamos pausando
        'session_id': data.get('session_id'),
        'timestamp': data.get('timestamp')
    }
    return JsonResponse(response_data)


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def resume_monitoring(request):
    """Reanuda la sesión actual"""
    success, message, data = controller.resume_session()
    
    if not success:
        return JsonResponse({
            'status': 'error',
            'message': message
        }, status=400)
    
    response_data = {
        'status': 'success',
        'message': message,
        'total_blinks': data.get('blink_count', 0),  # Garantizar ambos campos
        'blink_count': data.get('blink_count', 0),   # Para retrocompatibilidad
        'is_paused': data.get('is_paused', False),   # False porque estamos reanudando
        'session_id': data.get('session_id'),
        'timestamp': data.get('timestamp')
    }
    return JsonResponse(response_data)


@login_required
def session_metrics(request):
    """Retorna las métricas actuales de la sesión"""
    return JsonResponse(controller.get_metrics())


@login_required
def camera_status(request):
    """Verifica el estado de la cámara y devuelve información de diagnóstico"""
    
    # Verificar si camera_manager está inicializado
    if not controller.camera_manager:
        return JsonResponse({
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
        'camera_running': controller.camera_manager.is_running,
        'video_initialized': controller.camera_manager.video is not None,
        'video_opened': controller.camera_manager.video.isOpened() if controller.camera_manager.video else False,
        'session_active': controller.camera_manager.session_id is not None,
        'is_paused': controller.camera_manager.is_paused,
        'error_count': controller.camera_manager.error_count,
    }
    
    try:
        if controller.camera_manager.video:
            frame_test = controller.camera_manager.video.read()[0]
            status['can_read_frames'] = frame_test
        else:
            status['can_read_frames'] = False
    except Exception as e:
        status['can_read_frames'] = False
        status['read_error'] = str(e)
    
    return JsonResponse({
        'status': 'success',
        'camera_status': status,
        'message': 'Estado de la cámara obtenido correctamente'
    })


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def snooze_break_reminder(request):
    """Pospone el recordatorio de descanso por X minutos"""
    try:
        data = json.loads(request.body)
        snooze_minutes = data.get('minutes', 5)  # default: 5 minutos
        
        # Ajustar el último recordatorio para posponer
        controller.last_break_reminder = time.time()
        
        logging.info(f"[BREAK] Recordatorio pospuesto por {snooze_minutes} minutos")
        
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
    """Marca que el usuario tomó un descanso y resetea el recordatorio"""
    try:
        if not controller.user_config:
            return JsonResponse({
                'status': 'error',
                'message': 'No hay sesión activa'
            }, status=400)
        
        user = controller.user_config
        
        # Resetear contador de recordatorios
        controller.last_break_reminder = time.time()
        
        logging.info(f"[BREAK] Descanso registrado para {user.username}")
        
        return JsonResponse({
            'status': 'success',
            'message': 'Descanso registrado correctamente'
        })
        
    except Exception as e:
        logging.error(f"[BREAK] Error al registrar descanso: {e}")
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=400)


# Eliminado: validate_enhanced_config (per-user) ya no aplica con configuración global
