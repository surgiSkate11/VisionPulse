from django.shortcuts import render
from django.views.generic import TemplateView
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from apps.security.components.menu_module import MenuModule
from apps.security.components.group_session import UserGroupSession
from django.db.models import Avg, Count, Q, Sum
from django.http import JsonResponse, HttpResponseBadRequest, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from django.core.cache import cache
import cv2
import numpy as np
import mediapipe as mp
import base64
import threading
import time
from math import hypot
from .models import MonitorSession, BlinkEvent, AlertEvent

# Inicializar MediaPipe Face Mesh con alta precisión
mp_face_mesh = mp.solutions.face_mesh
face_mesh = mp_face_mesh.FaceMesh(
    max_num_faces=1,
    refine_landmarks=True,
    min_detection_confidence=0.5,
    min_tracking_confidence=0.5
)

# Índices de los landmarks para cada ojo (MediaPipe Face Mesh)
LEFT_EYE = [33, 160, 158, 133, 153, 144]   # Puntos del ojo izquierdo
RIGHT_EYE = [362, 385, 387, 263, 373, 380]  # Puntos del ojo derecho

# ============================================================================
# VARIABLES GLOBALES PARA CONTROL DE WEBCAM Y SESIÓN
# ============================================================================
webcam_global = None
webcam_lock = threading.Lock()
streaming_active = False
current_session_id = None
last_faces_count = 0
last_eyes_count = 0
last_avg_ear = 0.0

# Configuración de detección de parpadeos
EAR_CALIBRATION_FRAMES = 60  # Frames para calibración inicial (2 segundos a 30 FPS)
EAR_WINDOW_SIZE = 5         # Tamaño de la ventana para suavizado
EAR_STD_THRESHOLD = 1.5     # Desviaciones estándar para detección de parpadeos
MIN_BLINK_FRAMES = 2        # Mínimo de frames para considerar un parpadeo
MAX_BLINK_FRAMES = 7        # Máximo de frames para un parpadeo normal
DEBOUNCE_FRAMES = 5         # Frames de espera entre parpadeos

# Buffers y contadores
ear_history = []            # Historial de valores EAR para calibración
blink_counter = 0          # Contador total de parpadeos
closed_counter = 0         # Contador de frames con ojos cerrados
open_counter = 0           # Contador de frames con ojos abiertos
last_blink_time = 0       # Timestamp del último parpadeo detectado

def calculate_ear(eye_points):
    try:
        points = np.array(eye_points, dtype=np.float32)
        A = hypot(points[1][0] - points[5][0], points[1][1] - points[5][1])
        B = hypot(points[2][0] - points[4][0], points[2][1] - points[4][1])
        C = hypot(points[0][0] - points[3][0], points[0][1] - points[3][1])
        if C < 1e-3:
            return None
        ear = (0.4 * A + 0.6 * B) / (2.0 * C)
        return ear if 0.05 <= ear <= 0.6 else None
    except Exception:
        return None

def detect_blink(current_ear, threshold=None):
    """
    Detecta parpadeos usando un umbral dinámico y análisis de la señal EAR.
    """
    global ear_history, closed_counter, open_counter, last_blink_time, blink_counter
    
    current_time = time.time()
    
    # Si no hay suficientes datos para el umbral, recolectar datos
    if len(ear_history) < EAR_CALIBRATION_FRAMES:
        if current_ear is not None:
            ear_history.append(current_ear)
        return False
    
    # Calcular umbral dinámico si no se proporciona
    if threshold is None:
        mean_ear = np.mean(ear_history)
        std_ear = np.std(ear_history)
        threshold = mean_ear - (EAR_STD_THRESHOLD * std_ear)
    
    # Detectar estado de los ojos
    if current_ear is not None:
        # Actualizar historial móvil
        ear_history.append(current_ear)
        if len(ear_history) > EAR_CALIBRATION_FRAMES:
            ear_history.pop(0)
        
        # Verificar si los ojos están cerrados
        if current_ear < threshold:
            closed_counter += 1
            open_counter = 0
        else:
            # Si los ojos están abiertos después de estar cerrados
            if closed_counter >= MIN_BLINK_FRAMES and closed_counter <= MAX_BLINK_FRAMES:
                # Verificar tiempo desde último parpadeo (debouncing)
                if current_time - last_blink_time > (DEBOUNCE_FRAMES / 30.0):
                    blink_counter += 1
                    last_blink_time = current_time
                    closed_counter = 0
                    return True
            
            closed_counter = 0
            open_counter += 1
    
    return False

def draw_eye_landmarks(frame, left_eye_points, right_eye_points, ear_value, blink_detected, blink_counter, ear_history_len):
    output = frame.copy()
    height, width = frame.shape[:2]

    # overlay semitransparente para panel
    info_panel_height = 160
    info_panel_y = height - info_panel_height
    overlay = output.copy()
    cv2.rectangle(overlay, (0, info_panel_y), (width, height), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.35, output, 0.65, 0, output)

    def draw_eye(points, is_left):
        if len(points) == 6:
            pts = np.array(points, dtype=np.int32)
            color = (0, 0, 255) if blink_detected else (0, 255, 0)
            cv2.polylines(output, [pts], True, color, 2)
            cv2.polylines(output, [pts], True, (255, 255, 255), 1)
            for i, p in enumerate(pts):
                cv2.circle(output, tuple(p), 3, (0, 165, 255), -1)
                cv2.circle(output, tuple(p), 1, (255, 255, 255), -1)

    draw_eye(left_eye_points, True)
    draw_eye(right_eye_points, False)

    # texto y métricas (formateos seguros)
    info_x = 18
    info_y = info_panel_y + 28
    title_bg_color = (0, 0, 255) if blink_detected else (0, 128, 0)
    cv2.rectangle(output, (10, info_y - 20), (220, info_y), title_bg_color, -1)
    cv2.putText(output, "MEDICIONES", (15, info_y - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,255,255), 1)

    ear_text = f"{ear_value:.3f}" if (ear_value is not None) else "--"
    cv2.putText(output, f"EAR: {ear_text}", (info_x, info_y + 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255,255,255), 2)
    status = "PARPADEO" if blink_detected else "ABIERTO"
    status_color = (0,0,255) if blink_detected else (0,255,0)
    cv2.putText(output, f"Estado: {status}", (info_x, info_y + 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, status_color, 2)
    cv2.putText(output, f"Parpadeos: {blink_counter}", (info_x, info_y + 92), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,255), 2)

    if ear_history_len < EAR_CALIBRATION_FRAMES:
        progress = int(ear_history_len / EAR_CALIBRATION_FRAMES * 100)
        cv2.putText(output, f"Calibrando: {progress}%", (info_x, info_y + 122), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,255,255), 2)

    return output

def generate_frames():
    global webcam_global, streaming_active, current_session_id
    global last_faces_count, last_eyes_count, last_avg_ear
    global blink_counter, ear_history

    print("=== GENERATE_FRAMES INICIADO (DETECCIÓN MEJORADA) ===")
    blink_counter = 0
    ear_history = []
    frame_count = 0

    # inicializar webcam si no está abierta
    with webcam_lock:
        if webcam_global is None:
            webcam_global = cv2.VideoCapture(0)
            webcam_global.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            webcam_global.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            webcam_global.set(cv2.CAP_PROP_FPS, 30)
        cap = webcam_global

    # crear FaceMesh en contexto local (evita condiciones de carrera)
    mp_face_mesh_local = mp.solutions.face_mesh
    try:
        with mp_face_mesh_local.FaceMesh(
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        ) as face_mesh_local:
            while streaming_active:
                frame_count += 1
                with webcam_lock:
                    if cap is None or not cap.isOpened():
                        print("Webcam no disponible")
                        break
                    ret, frame = cap.read()
                if not ret:
                    print("No se pudo leer frame")
                    break

                frame = cv2.flip(frame, 1)
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                results = None
                try:
                    results = face_mesh_local.process(frame_rgb)
                except Exception as e:
                    # si MediaPipe falla en un frame, no interrumpir todo el stream
                    print("MediaPipe error en este frame:", e)
                    results = None

                current_ear = None
                blink_detected = False
                faces_count = 0
                left_eye_points = []
                right_eye_points = []

                if results and results.multi_face_landmarks:
                    faces_count = len(results.multi_face_landmarks)
                    face_landmarks = results.multi_face_landmarks[0]
                    h, w = frame.shape[:2]
                    for idx in LEFT_EYE:
                        lm = face_landmarks.landmark[idx]
                        left_eye_points.append([int(lm.x * w), int(lm.y * h)])
                    for idx in RIGHT_EYE:
                        lm = face_landmarks.landmark[idx]
                        right_eye_points.append([int(lm.x * w), int(lm.y * h)])
                    if len(left_eye_points) == 6 and len(right_eye_points) == 6:
                        l_ear = calculate_ear(left_eye_points)
                        r_ear = calculate_ear(right_eye_points)
                        if l_ear is not None and r_ear is not None:
                            current_ear = min(l_ear, r_ear)
                            # detectar parpadeo
                            if detect_blink(current_ear):
                                blink_detected = True
                                blink_counter += 0  # detect_blink ya incrementa; dejar por claridad

                # actualizar métricas de debug
                try:
                    last_faces_count = faces_count
                    last_eyes_count = 2 if faces_count > 0 else 0
                    last_avg_ear = float(current_ear) if current_ear is not None else last_avg_ear
                except Exception:
                    pass

                # dibujar información y landmarks (usar función única para panel + ojos)
                frame_out = draw_eye_landmarks(frame, left_eye_points, right_eye_points,
                                               current_ear, blink_detected, blink_counter, len(ear_history))

                # codificar frame (JPEG calidad 80 para menor carga)
                encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), 80]
                success, buffer = cv2.imencode('.jpg', frame_out, encode_params)
                if not success:
                    # saltar frame si no se pudo codificar
                    continue
                frame_bytes = buffer.tobytes()
                try:
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
                except GeneratorExit:
                    # cliente desconectado
                    break

    except Exception as e:
        print("Error crítico en generate_frames:", e)
    finally:
        # cleanup garantizado
        with webcam_lock:
            if webcam_global is not None:
                try:
                    webcam_global.release()
                except Exception:
                    pass
                webcam_global = None
        print("=== GENERATE_FRAMES TERMINADO ===")
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
            
            s.duration_hms = formatted
            recent_sessions.append(s)
        
        context['recent_sessions'] = recent_sessions
        
        # Tiempo total de monitoreo
        total_seconds = (
            MonitorSession.objects
            .filter(user=self.request.user)
            .aggregate(total_time=Sum('duration_seconds'))['total_time'] or 0
        )
        
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
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

@login_required
def session_metrics(request):
    """Return current session metrics (avg_ear, total_blinks) as JSON.
    This is polled by the front-end to show live metrics while streaming.
    """
    global current_session_id

    if current_session_id is None:
        return JsonResponse({
            'status': 'no_session',
            'message': 'No active monitoring session',
            'avg_ear': 0.0,
            'total_blinks': 0,
            'faces': last_faces_count,
            'eyes': last_eyes_count,
            'debug_avg_ear': last_avg_ear
        })

    try:
        session = MonitorSession.objects.get(id=current_session_id)
        return JsonResponse({
            'status': 'success',
            'avg_ear': session.avg_ear or 0.0,
            'total_blinks': session.total_blinks or 0,
            'faces': last_faces_count,
            'eyes': last_eyes_count,
            'debug_avg_ear': last_avg_ear
        })
    except MonitorSession.DoesNotExist:
        return JsonResponse({
            'status': 'error',
            'message': 'Session not found',
            'avg_ear': 0.0,
            'total_blinks': 0,
            'faces': last_faces_count,
            'eyes': last_eyes_count,
            'debug_avg_ear': last_avg_ear
        })

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
    
    # Detener streaming
    streaming_active = False
    time.sleep(0.2)  # Dar tiempo para que el generador termine
    
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
    
    return JsonResponse({
        'status': 'success',
        'message': 'Webcam detenida y sesión finalizada',
        'session_id': session_id,
        'duration_seconds': duration
    })

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
    
    cache.delete(f'monitor:{session.id}:blink_count')
    
    return JsonResponse({
        'ok': True,
        'duration_seconds': session.duration_seconds
    })