from django.shortcuts import render
from django.views.generic import TemplateView
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from apps.security.components.menu_module import MenuModule
from apps.security.components.group_session import UserGroupSession
from django.db.models import Avg, Count, Q
from django.http import JsonResponse, HttpResponseBadRequest, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from django.core.cache import cache
from django.db.models import Sum
# Image processing
import cv2
import numpy as np
import base64
import threading
import time
from .models import MonitorSession, BlinkEvent, AlertEvent

# Load Haar cascades for face and eye detection
try:
    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
    eye_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_eye.xml')
except Exception:
    face_cascade = None
    eye_cascade = None


# ============================================================================
# VARIABLES GLOBALES PARA CONTROL DE WEBCAM Y SESIÓN
# ============================================================================
webcam_global = None
webcam_lock = threading.Lock()
streaming_active = False
current_session_id = None  # Para relacionar el streaming con una sesión activa


# ============================================================================
# FUNCIONES AUXILIARES
# ============================================================================
def _decode_base64_image(data_url):
    """Decodifica una imagen enviada como data URL (base64)"""
    if not data_url:
        return None
    if ',' in data_url:
        header, b64data = data_url.split(',', 1)
    else:
        b64data = data_url
    try:
        img_bytes = base64.b64decode(b64data)
        arr = np.frombuffer(img_bytes, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        return img
    except Exception:
        return None


def _estimate_eye_metrics(gray, eyes):
    """
    Calcula métricas de apertura ocular.
    Returns: avg_ear (0..1) y blink_detected (bool)
    """
    if len(eyes) == 0:
        return 0.0, False
    ratios = []
    for (ex, ey, ew, eh) in eyes:
        if ew <= 0:
            continue
        ratios.append(eh / float(ew))
    if not ratios:
        return 0.0, False
    avg = float(sum(ratios)) / len(ratios)
    # Normalizar a rango 0..1
    norm = (avg - 0.08) / (0.4 - 0.08)
    avg_ear = max(0.0, min(1.0, norm))
    # Detectar parpadeo si avg_ear cae bajo umbral
    blink = avg_ear < 0.15
    return avg_ear, blink


# ============================================================================
# VISTAS DE TEMPLATE
# ============================================================================
@method_decorator(login_required, name='dispatch')
class ModuloTemplateView(TemplateView):
    template_name = 'monitoring/MHome.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = "VisionPulse - Monitoreo"
        
        user_session = UserGroupSession(self.request)
        user_session.set_group_session()
        MenuModule(self.request).fill(context)
        
        # Extraer menús
        herramientas_menu = None
        sidebar_menu = None
        for menu_item in context.get('menu_list', []):
            menu_name = getattr(menu_item['menu'], 'name', '').lower()
            if menu_name == 'herramientas':
                herramientas_menu = menu_item
            if menu_name == 'sidebar':
                sidebar_menu = menu_item
        context['herramientas_menu'] = herramientas_menu
        context['sidebar_menu'] = sidebar_menu


        # Sesiones recientes
        sessions = (
            MonitorSession.objects
            .filter(user=self.request.user)
            .order_by('-start_time')[:5]
        )

        # Convertir duración a h-m-s
        recent_sessions = []
        for s in sessions:
            total = s.duration_seconds or 0
            hours, remainder = divmod(total, 3600)
            minutes, seconds = divmod(remainder, 60)

            if hours > 0:
                formatted = f"{hours}h {minutes}m {seconds}s"
            elif minutes > 0:
                formatted = f"{minutes}m {seconds}s"
            else:
                formatted = f"{seconds}s"

            # atributo dinámico para usar en el template
            s.duration_hms = formatted
            recent_sessions.append(s)

        context['recent_sessions'] = recent_sessions

        
        #
        total_seconds = (
        MonitorSession.objects
        .filter(user=self.request.user)
        .aggregate(total_time=Sum('duration_seconds'))['total_time'] or 0)
        
        # Convertir a horas:minutos:segundos
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)

        # Guardar en el contexto en formato legible
        context['total_monitoring_time'] = f"{hours}h {minutes}m {seconds}s"
                
        return context


@method_decorator(login_required, name='dispatch')
class WebcamTestView(TemplateView):
    template_name = 'monitoring/webcam_test.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = "VisionPulse - Monitoreo en Tiempo Real"
        
        user_session = UserGroupSession(self.request)
        user_session.set_group_session()
        MenuModule(self.request).fill(context)
        
        return context


@method_decorator(login_required, name='dispatch')
class SessionListView(TemplateView):
    template_name = 'monitoring/session_list.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = "VisionPulse - Historial de Sesiones"
        
        user_session = UserGroupSession(self.request)
        user_session.set_group_session()
        MenuModule(self.request).fill(context)

        sessions = MonitorSession.objects.filter(
            user=self.request.user
        ).order_by('-start_time')

        for session in sessions:
            session.alert_count = session.alerts.count()
            session.blink_count = session.blink_events.count()
            session.focus_score = session.focus_percent or (
                100 * (1 - (session.alerts_count or 0) / max(session.total_blinks or 1, 1))
            )

        context['sessions'] = sessions
        return context


@method_decorator(login_required, name='dispatch')
class SessionDetailView(TemplateView):
    template_name = 'monitoring/session_detail.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        session_id = kwargs.get('session_id')
        
        try:
            session = MonitorSession.objects.get(
                id=session_id,
                user=self.request.user
            )
        except MonitorSession.DoesNotExist:
            from django.http import Http404
            raise Http404("Session not found")

        user_session = UserGroupSession(self.request)
        user_session.set_group_session()
        MenuModule(self.request).fill(context)

        # Timeline de eventos
        blinks = list(session.blink_events.all())
        alerts = list(session.alerts.all())

        events = []
        for blink in blinks:
            events.append({
                'type': 'blink',
                'timestamp': blink.timestamp,
                'duration': blink.duration_ms
            })
        for alert in alerts:
            events.append({
                'type': 'alert',
                'timestamp': alert.triggered_at,
                'alert_type': alert.get_alert_type_display(),
                'resolved': alert.resolved,
                'resolved_at': alert.resolved_at
            })
        events.sort(key=lambda x: x['timestamp'])

        context.update({
            'title': f"Sesión de Monitoreo - {session.start_time:%Y-%m-%d %H:%M}",
            'session': session,
            'events': events,
            'blink_count': len(blinks),
            'alert_count': len(alerts),
            'focus_score': session.focus_percent or (
                100 * (1 - (session.alerts_count or 0) / max(session.total_blinks or 1, 1))
            )
        })
        return context


# ============================================================================
# STREAMING DE VIDEO CON DETECCIONES
# ============================================================================
def generate_frames():
    """
    Genera frames de video con detección facial y de ojos.
    Integrado con el sistema de sesiones para guardar métricas.
    """
    global webcam_global, streaming_active, current_session_id
    
    print("=== GENERATE_FRAMES INICIADO ===")
    
    # Inicializar webcam si no existe
    with webcam_lock:
        if webcam_global is None:
            webcam_global = cv2.VideoCapture(0)
            webcam_global.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            webcam_global.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    
    # Obtener sesión activa si existe
    session = None
    if current_session_id:
        try:
            session = MonitorSession.objects.get(id=current_session_id)
        except MonitorSession.DoesNotExist:
            pass
    
    frame_count = 0
    
    # Loop principal de streaming
    while streaming_active:
        with webcam_lock:
            if webcam_global is None or not webcam_global.isOpened():
                print("Webcam no disponible, saliendo del loop")
                break
            ret, frame = webcam_global.read()
        
        if not ret:
            print("No se pudo leer frame")
            break
        
        frame_count += 1
        
        # Realizar detecciones
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        faces = []
        eyes = []
        
        if face_cascade is not None:
            faces = face_cascade.detectMultiScale(
                gray, 
                scaleFactor=1.1, 
                minNeighbors=5, 
                minSize=(60, 60)
            )
            
            for (x, y, w, h) in faces:
                # Dibujar rectángulo alrededor del rostro
                cv2.rectangle(frame, (x, y), (x+w, y+h), (255, 0, 0), 2)
                
                # Detectar ojos dentro del rostro
                roi_gray = gray[y:y+h, x:x+w]
                if eye_cascade is not None:
                    detected_eyes = eye_cascade.detectMultiScale(roi_gray)
                    for (ex, ey, ew, eh) in detected_eyes:
                        eyes.append((x + ex, y + ey, ew, eh))
                        cv2.rectangle(
                            frame, 
                            (x+ex, y+ey), 
                            (x+ex+ew, y+ey+eh), 
                            (0, 255, 0), 
                            2
                        )
        
        # Calcular métricas de ojos
        avg_ear, blink_detected = _estimate_eye_metrics(gray, eyes)
        
        # Actualizar sesión si existe (cada 10 frames para no saturar la BD)
        if session and frame_count % 10 == 0:
            try:
                # Actualizar EAR promedio
                if session.avg_ear is None:
                    session.avg_ear = avg_ear
                else:
                    session.avg_ear = (session.avg_ear + avg_ear) / 2.0
                
                # Detectar y registrar parpadeos
                if blink_detected:
                    cache_key = f'monitor:{session.id}:last_blink'
                    last_blink = cache.get(cache_key, False)
                    
                    if not last_blink:
                        # Nuevo parpadeo detectado
                        session.total_blinks = (session.total_blinks or 0) + 1
                        BlinkEvent.objects.create(
                            session=session,
                            timestamp=timezone.now()
                        )
                        cache.set(cache_key, True, timeout=2)
                        
                        # Incrementar contador de parpadeos para alertas
                        blink_count_key = f'monitor:{session.id}:blink_count'
                        bc = cache.get(blink_count_key, 0) + 1
                        cache.set(blink_count_key, bc, timeout=3600)
                        
                        # Generar alerta si hay muchos parpadeos
                        if bc > 30:
                            session.alerts_count = (session.alerts_count or 0) + 1
                            AlertEvent.objects.create(
                                session=session,
                                alert_type=AlertEvent.ALERT_FATIGUE,
                                triggered_at=timezone.now(),
                                metadata={'blink_count': bc}
                            )
                            cache.set(blink_count_key, 0, timeout=3600)
                else:
                    cache_key = f'monitor:{session.id}:last_blink'
                    cache.set(cache_key, False, timeout=3600)
                
                session.save()
            except Exception as e:
                print(f"Error actualizando sesión: {e}")
        
        # Mostrar información en el frame
        cv2.putText(
            frame, 
            f'Rostros: {len(faces)}', 
            (10, 30), 
            cv2.FONT_HERSHEY_SIMPLEX, 
            0.7, 
            (255, 255, 255), 
            2
        )
        cv2.putText(
            frame, 
            f'Ojos: {len(eyes)}', 
            (10, 60), 
            cv2.FONT_HERSHEY_SIMPLEX, 
            0.7, 
            (255, 255, 255), 
            2
        )
        cv2.putText(
            frame, 
            f'EAR: {avg_ear:.2f}', 
            (10, 90), 
            cv2.FONT_HERSHEY_SIMPLEX, 
            0.7, 
            (255, 255, 255), 
            2
        )
        cv2.putText(
            frame, 
            f'Parpadeo: {"SI" if blink_detected else "NO"}', 
            (10, 120), 
            cv2.FONT_HERSHEY_SIMPLEX, 
            0.7, 
            (255, 255, 255), 
            2
        )
        
        if session:
            cv2.putText(
                frame, 
                f'Sesion: {session.id}', 
                (10, 150), 
                cv2.FONT_HERSHEY_SIMPLEX, 
                0.5, 
                (0, 255, 255), 
                1
            )
            cv2.putText(
                frame, 
                f'Parpadeos totales: {session.total_blinks or 0}', 
                (10, 175), 
                cv2.FONT_HERSHEY_SIMPLEX, 
                0.5, 
                (0, 255, 255), 
                1
            )
        
        # Codificar frame como JPEG
        ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        frame_bytes = buffer.tobytes()
        
        # Yield frame en formato multipart
        yield (b'--frame\r\n'
                b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        
        time.sleep(0.03)  # ~30 FPS
    
    # Limpiar recursos al salir del loop
    print("=== GENERATE_FRAMES TERMINADO ===")
    with webcam_lock:
        if webcam_global is not None:
            webcam_global.release()
            webcam_global = None
        cv2.destroyAllWindows()


@login_required
def video_feed(request):
    """Vista que streaming de video con detecciones en tiempo real"""
    global streaming_active
    
    print("=== VIDEO_FEED LLAMADO ===")
    streaming_active = True
    
    return StreamingHttpResponse(
        generate_frames(),
        content_type='multipart/x-mixed-replace; boundary=frame'
    )


# ============================================================================
# CONTROL DE SESIONES DE MONITOREO
# ============================================================================
@login_required
@require_http_methods(["POST"])
def start_webcam_test(request):
    """
    Iniciar webcam y crear una nueva sesión de monitoreo.
    Retorna el session_id para tracking.
    """
    global webcam_global, streaming_active, current_session_id
    
    print("=== START_WEBCAM_TEST LLAMADO ===")
    
    with webcam_lock:
        if webcam_global is None:
            webcam_global = cv2.VideoCapture(0)
            if not webcam_global.isOpened():
                webcam_global = None
                return JsonResponse({
                    'status': 'error', 
                    'message': 'No se pudo abrir la webcam'
                })
    
    # Crear nueva sesión de monitoreo
    try:
        session = MonitorSession.objects.create(
            user=request.user,
            start_time=timezone.now(),
            metadata={}
        )
        current_session_id = session.id
        
        # Inicializar cache para detección de parpadeos
        cache.set(f'monitor:{session.id}:last_blink', False, timeout=3600)
        cache.set(f'monitor:{session.id}:blink_count', 0, timeout=3600)
        
        streaming_active = True
        
        print(f"Sesión creada: {session.id}")
        
        return JsonResponse({
            'status': 'success',
            'message': 'Webcam iniciada y sesión creada',
            'session_id': session.id
        })
    except Exception as e:
        print(f"Error creando sesión: {e}")
        return JsonResponse({
            'status': 'error',
            'message': f'Error al crear sesión: {str(e)}'
        })


@login_required
@require_http_methods(["POST"])
def stop_webcam_test(request):
    """
    Detener webcam y finalizar sesión de monitoreo.
    """
    global webcam_global, streaming_active, current_session_id
    
    print("=== STOP_WEBCAM_TEST LLAMADO ===")
    print(f"streaming_active antes: {streaming_active}")
    
    # Detener streaming PRIMERO
    streaming_active = False
    time.sleep(0.2)  # Dar tiempo para que el generador termine
    
    print(f"streaming_active después: {streaming_active}")
    
    # Finalizar sesión si existe
    if current_session_id:
        try:
            session = MonitorSession.objects.get(
                id=current_session_id,
                user=request.user
            )
            session.end_time = timezone.now()
            session.save()
            
            # Limpiar cache
            cache.delete(f'monitor:{session.id}:last_blink')
            cache.delete(f'monitor:{session.id}:blink_count')
            
            print(f"Sesión finalizada: {session.id}")
            session_id = session.id
            duration = session.duration_seconds
        except MonitorSession.DoesNotExist:
            session_id = None
            duration = 0
    else:
        session_id = None
        duration = 0
    
    current_session_id = None
    
    # Liberar recursos de la webcam
    with webcam_lock:
        if webcam_global is not None:
            webcam_global.release()
            webcam_global = None
            cv2.destroyAllWindows()
            print("Webcam liberada correctamente")
    
    return JsonResponse({
        'status': 'success',
        'message': 'Webcam detenida y sesión finalizada',
        'session_id': session_id,
        'duration_seconds': duration
    })


# ============================================================================
# ENDPOINTS ADICIONALES (COMPATIBILIDAD CON SISTEMA ANTERIOR)
# ============================================================================
@login_required
@csrf_exempt
def start_session(request):
    """Crear una nueva sesión de monitoreo (API alternativa)"""
    if request.method != 'POST':
        return HttpResponseBadRequest('POST required')
    
    session = MonitorSession.objects.create(
        user=request.user,
        start_time=timezone.now(),
        metadata={}
    )
    
    cache.set(f'monitor:{session.id}:last_blink', False, timeout=3600)
    cache.set(f'monitor:{session.id}:blink_count', 0, timeout=3600)
    
    return JsonResponse({
        'session_id': session.id
        })


@login_required
@csrf_exempt
def stop_session(request):
    """Finalizar sesión de monitoreo (API alternativa)"""
    if request.method != 'POST':
        return HttpResponseBadRequest('POST required')
    
    session_id = request.POST.get('session_id')
    if not session_id:
        try:
            import json
            payload = json.loads(request.body.decode('utf-8'))
            session_id = payload.get('session_id')
        except Exception:
            return HttpResponseBadRequest('session_id required')
    
    try:
        session = MonitorSession.objects.get(id=session_id, user=request.user)
    except MonitorSession.DoesNotExist:
        return HttpResponseBadRequest('invalid session')
    
    session.end_time = timezone.now()
    session.save()
    
    cache.delete(f'monitor:{session.id}:last_blink')
    cache.delete(f'monitor:{session.id}:blink_count')
    
    return JsonResponse({
        'ok': True,
        'duration_seconds': session.duration_seconds
    })