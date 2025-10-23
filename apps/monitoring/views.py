from django.shortcuts import render, get_object_or_404
from django.views.generic import TemplateView, ListView, DetailView
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.http import JsonResponse, HttpResponseBadRequest, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from django.conf import settings
from django.core.cache import cache
from django.db.models import Avg, Count, Q, Sum
from .models import MonitorSession, BlinkEvent, AlertEvent, SessionPause
from apps.security.components.menu_module import MenuModule
from apps.security.components.sidebar_menu_mixin import SidebarMenuMixin
from apps.security.components.group_session import UserGroupSession
import cv2
import mediapipe as mp
import threading
import time
from math import hypot

# --- Configuración de MediaPipe Face Mesh ---
mp_face_mesh = mp.solutions.face_mesh
face_mesh = mp_face_mesh.FaceMesh(
    max_num_faces=1,
    refine_landmarks=True,
    min_detection_confidence=0.5,
    min_tracking_confidence=0.5
)

# Índices de landmarks para ojos
LEFT_EYE = [33, 160, 158, 133, 153, 144]
RIGHT_EYE = [362, 385, 387, 263, 373, 380]

# --- Variables Globales ---
camera_instance = None
camera_lock = threading.Lock()

# --- Configuración de Detección ---
VERTICAL_DISTANCE_THRESHOLD = 5  # Pixeles - cuando es menor, ojos cerrados
EAR_THRESHOLD = 0.20  # Umbral EAR como respaldo
MIN_BLINK_DURATION = 0.01  # 50ms mínimo
MAX_BLINK_DURATION = 0.35  # 350ms máximo
DEBOUNCE_TIME = 0.15  # 150ms entre parpadeos

# --- Vistas Principales ---

@method_decorator(login_required, name='dispatch')
class LiveMonitoringView(SidebarMenuMixin, TemplateView):
    """Vista principal para monitoreo en vivo."""
    template_name = 'monitoring/live_session.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Monitoreo en Vivo'
        
        # Añadir configuración del usuario
        context['user_config'] = {
            'ear_threshold': getattr(self.request.user, 'ear_threshold', EAR_THRESHOLD),
            'blink_window': getattr(self.request.user, 'blink_window_frames', 3),
        }
        return context

@method_decorator(login_required, name='dispatch')
class SessionListView(SidebarMenuMixin, ListView):
    """Vista de historial de sesiones."""
    template_name = 'monitoring/session_list.html'
    context_object_name = 'sessions'
    paginate_by = 10

    def get_queryset(self):
        return MonitorSession.objects.filter(
            user=self.request.user
        ).order_by('-start_time').select_related('user')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Historial de Sesiones'
        
        # Añadir estadísticas globales
        context['stats'] = {
            'total_sessions': self.get_queryset().count(),
            'total_duration': self.get_queryset().aggregate(
                Sum('duration_seconds')
            )['duration_seconds__sum'] or 0,
            'avg_blinks': self.get_queryset().aggregate(
                Avg('total_blinks')
            )['total_blinks__avg'] or 0,
        }
        return context

@method_decorator(login_required, name='dispatch')
class SessionDetailView(SidebarMenuMixin, DetailView):
    """Vista detallada de una sesión."""
    template_name = 'monitoring/session_detail.html'
    context_object_name = 'session'
    pk_url_kwarg = 'session_id'  # Coincide con el <int:session_id> en urls.py
    
    def get_queryset(self):
        return MonitorSession.objects.filter(
            user=self.request.user
        ).prefetch_related('blink_events', 'alerts')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        session = self.get_object()
        context['title'] = f'Sesión del {session.start_time:%d/%m/%Y %H:%M}'
        
        # Combinar eventos cronológicamente
        events = []
        
        for blink in session.blink_events.all():
            events.append({
                'type': 'blink',
                'timestamp': blink.timestamp,
                'duration': blink.duration_ms
            })
            
        for alert in session.alerts.all():
            events.append({
                'type': 'alert',
                'timestamp': alert.triggered_at,
                'alert_type': alert.get_alert_type_display(),
                'resolved': alert.resolved,
                'resolved_at': alert.resolved_at
            })
        
        # Ordenar por timestamp
        context['events'] = sorted(events, key=lambda x: x['timestamp'])
        
        # Añadir métricas
        context['metrics'] = {
            'blinks_per_minute': (session.total_blinks * 60) / (session.duration_seconds or 1),
            'focus_time': (session.focus_percent or 0) * session.duration_seconds / 100,
            'alert_count': session.alerts_count,
        }
        
        return context

# --- Lógica de Procesamiento de Video ---
class VideoProcessor:
    """Clase para procesar frames y detectar eventos oculares."""
    
    def __init__(self):
        self.blink_state = "OPEN"
        self.blink_start = None
        self.last_blink_time = 0
        self.blink_counter = 0
        self.ear_values = []
        self.face_detected = False
    
    def calculate_ear(self, landmarks, eye_indices):
        """Calcula Eye Aspect Ratio (EAR) para un ojo."""
        try:
            # Obtener coordenadas normalizadas
            points = [landmarks[idx] for idx in eye_indices]
            
            # Calcular distancias verticales
            v1 = hypot(points[1].x - points[5].x, points[1].y - points[5].y)
            v2 = hypot(points[2].x - points[4].x, points[2].y - points[4].y)
            
            # Calcular distancia horizontal
            h = hypot(points[0].x - points[3].x, points[0].y - points[3].y)
            
            # Calcular EAR
            if h == 0:
                return 0
            return (v1 + v2) / (2.0 * h)
            
        except Exception as e:
            print(f"Error calculando EAR: {str(e)}")
            return None
    
    def process_frame(self, frame):
        """Procesa un frame y detecta eventos oculares."""
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = face_mesh.process(frame_rgb)
        
        metrics = {
            'ear': 0,
            'face_detected': False,
            'blink_detected': False,
            'focus': 'No detectado'
        }
        
        if not results.multi_face_landmarks:
            self.face_detected = False
            return frame, metrics
        
        self.face_detected = True
        metrics['face_detected'] = True
        
        # Obtener landmarks del primer rostro
        face_landmarks = results.multi_face_landmarks[0].landmark
        
        # Calcular EAR promedio de ambos ojos
        left_ear = self.calculate_ear(face_landmarks, LEFT_EYE)
        right_ear = self.calculate_ear(face_landmarks, RIGHT_EYE)
        
        if left_ear and right_ear:
            ear = (left_ear + right_ear) / 2.0
            metrics['ear'] = ear
            self.ear_values.append(ear)
            
            # Mantener solo los últimos 30 valores (1 segundo a 30 fps)
            if len(self.ear_values) > 30:
                self.ear_values.pop(0)
            
            # Detectar parpadeo
            current_time = time.time()
            
            if ear < EAR_THRESHOLD:
                if self.blink_state == "OPEN":
                    self.blink_state = "CLOSING"
                    self.blink_start = current_time
                elif self.blink_state == "CLOSING":
                    if current_time - self.blink_start > MIN_BLINK_DURATION:
                        self.blink_state = "CLOSED"
            else:
                if self.blink_state == "CLOSED":
                    blink_duration = current_time - self.blink_start
                    if blink_duration < MAX_BLINK_DURATION:
                        if current_time - self.last_blink_time > DEBOUNCE_TIME:
                            self.blink_counter += 1
                            metrics['blink_detected'] = True
                            self.last_blink_time = current_time
                    self.blink_state = "OPEN"
                elif self.blink_state == "CLOSING":
                    self.blink_state = "OPEN"
        
        # Determinar foco basado en EAR y detección facial
        if self.face_detected:
            if len(self.ear_values) >= 10:
                avg_ear = sum(self.ear_values[-10:]) / 10
                if EAR_THRESHOLD * 0.8 <= avg_ear <= EAR_THRESHOLD * 1.5:
                    metrics['focus'] = 'Atento'
                else:
                    metrics['focus'] = 'Distraído'
        
        return frame, metrics

class VideoCamera:
    """Gestiona la captura y procesamiento de video."""
    
    def __init__(self, user):
        self.user = user
        self._internal_lock = threading.Lock()  # Lock único para todos los estados
        
        # Inicializar cámara con configuración optimizada
        self.video = cv2.VideoCapture(0)
        if not self.video.isOpened():
            self.video = cv2.VideoCapture(1)  # Intentar cámara alternativa
            if not self.video.isOpened():
                raise IOError("No se pudo abrir la cámara (índices 0 y 1)")
        
        # Configurar cámara para mejor rendimiento
        self.video.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self.video.set(cv2.CAP_PROP_FPS, 30)
        
        # Estados de control (protegidos por _internal_lock)
        self.is_running = True
        self.is_paused = False
        
        # Procesador de video
        self.processor = VideoProcessor()
        
        # Estado y métricas (protegidos por _internal_lock)
        self.current_ear = 0
        self.current_focus = "No detectado"
        self.face_detected = False
        self.blink_count = 0
        
        # Frame actual y durante pausa (protegidos por _internal_lock)
        self.last_frame = None
        self.last_metrics = None
        self.pause_frame = None
        self.pause_metrics = None
        
        # Control de tiempo
        self.last_frame_time = time.time()
        self.frame_interval = 1.0 / 30
    
    def __del__(self):
        self.release()
    
    def release(self):
        if self.video and self.video.isOpened():
            self.video.release()
    
    def get_frame(self):
        """Captura y procesa un frame con manejo mejorado de estados."""
        with self._internal_lock:
            if not self.is_running:
                return None, None
            
            if self.is_paused:
                # Durante la pausa, devolver el último frame guardado
                if self.pause_frame is not None:
                    return self.pause_frame, self.pause_metrics or {
                        'ear': self.current_ear,
                        'focus': 'Pausado',
                        'face_detected': self.face_detected,
                        'blink_detected': False,
                        'faces': 1 if self.face_detected else 0
                    }
                return None, None
        
        # Control de tasa de frames
        current_time = time.time()
        time_since_last = current_time - self.last_frame_time
        if time_since_last < self.frame_interval:
            time.sleep(max(0, self.frame_interval - time_since_last))
        
        # Capturar nuevo frame
        success, frame = self.video.read()
        if not success:
            return None, None
        
        try:
            # Procesar frame
            processed_frame, metrics = self.processor.process_frame(frame)
            
            # Codificar frame
            _, jpeg = cv2.imencode('.jpg', processed_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
            frame_data = jpeg.tobytes()
            
            with self._internal_lock:
                # Actualizar estado y métricas
                self.last_frame = frame_data
                self.last_metrics = metrics.copy()
                self.current_ear = metrics['ear']
                self.current_focus = metrics['focus']
                self.face_detected = metrics['face_detected']
                if metrics.get('blink_detected'):
                    self.blink_count += 1
                
                # Guardar frame para pausa si es necesario
                if not self.pause_frame:
                    self.pause_frame = frame_data
                    self.pause_metrics = metrics.copy()
                
                self.last_frame_time = current_time
            
            return frame_data, metrics
            
        except Exception as e:
            print(f"Error procesando frame: {e}")
            return None, None
    
    def generate_frames(self):
        """Generador de frames para streaming."""
        self.frame_count = 0
        
        while self.is_running:
            with self.lock:
                if not self.is_running:  # Verificar de nuevo dentro del lock
                    break
                
                frame_data, metrics = self.get_frame()
                
            if frame_data is None:
                time.sleep(0.1)  # Evitar CPU spinning si hay error de captura
                continue
            
            try:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame_data + b'\r\n\r\n')
                
                if not self.is_paused:
                    self.frame_count += 1
                    
            except Exception as e:
                print(f"Error en generate_frames: {e}")
                break

# --- API Endpoints ---

@login_required
def video_feed(request):
    """Stream de video de la cámara."""
    global camera_instance
    
    with camera_lock:
        if not camera_instance or not camera_instance.is_running:
            return HttpResponseBadRequest("No hay sesión activa")
    
    return StreamingHttpResponse(
        camera_instance.generate_frames(),
        content_type='multipart/x-mixed-replace; boundary=frame'
    )

@login_required
@csrf_exempt
@require_http_methods(["POST"])
def start_session(request):
    """Inicia una nueva sesión de monitoreo."""
    global camera_instance, current_session_id, streaming_active
    
    try:
        with camera_lock:
            # Detener sesión anterior si existe
            if camera_instance:
                camera_instance.is_running = False
                camera_instance.release()
            
            # Crear nueva instancia
            camera_instance = VideoCamera(request.user)
            
            # Activar streaming
            streaming_active = True
        
        # Crear sesión en BD
        session = MonitorSession.objects.create(
            user=request.user,
            start_time=timezone.now(),
            metadata={
                'client_info': request.META.get('HTTP_USER_AGENT'),
                'ear_threshold': EAR_THRESHOLD,
            }
        )
        
        # Guardar ID en la sesión y variable global
        request.session['monitoring_session_id'] = session.id
        current_session_id = session.id
        
        print(f"✓ Sesión iniciada: {session.id}")
        return JsonResponse({
            'status': 'success',
            'message': 'Sesión iniciada correctamente',
            'session_id': session.id
        })
        
    except Exception as e:
        print(f"Error al iniciar sesión: {str(e)}")
        if camera_instance:
            camera_instance.is_running = False
            camera_instance.release()
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)

@login_required
@csrf_exempt
@require_http_methods(["POST"])
def stop_session(request):
    """Detiene la sesión actual de monitoreo."""
    global camera_instance, current_session_id
    session_id = request.session.pop('monitoring_session_id', None)
    
    if not session_id:
        return JsonResponse({
            'status': 'error',
            'message': 'No hay sesión activa'
        }, status=400)
    
    try:
        session = MonitorSession.objects.get(id=session_id, user=request.user)
        
        with camera_lock:
            if camera_instance:
                # Si hay una pausa activa, finalizarla
                last_pause = session.pauses.filter(resume_time__isnull=True).last()
                if last_pause:
                    last_pause.resume_time = timezone.now()
                    last_pause.save()
                
                # Calcular métricas finales
                blinks = camera_instance.blink_count
                
                # Actualizar sesión
                session.end_time = timezone.now()
                session.total_blinks = blinks
                session.avg_ear = sum(camera_instance.processor.ear_values) / len(camera_instance.processor.ear_values) if camera_instance.processor.ear_values else None
                session.save()  # Esto llamará a calculate_active_duration()
                
                # Obtener duración activa
                duration = session.duration_seconds
                
                # Detener cámara
                camera_instance.is_running = False
                camera_instance.release()
                camera_instance = None
        
        # Limpiar variable global de sesión
        current_session_id = None
        
        return JsonResponse({
            'status': 'success',
            'message': 'Sesión finalizada correctamente',
            'session_id': session.id,
            'duration': int(duration),
            'blinks': blinks
        })
        
    except MonitorSession.DoesNotExist:
        return JsonResponse({
            'status': 'error',
            'message': 'Sesión no encontrada'
        }, status=404)

@login_required
def session_metrics(request):
    """Obtiene métricas en tiempo real de la sesión actual."""
    global camera_instance
    
    with camera_lock:
        if not camera_instance or not camera_instance.is_running:
            return JsonResponse({
                'ear': '--',
                'focus': 'Inactivo',
                'face_detected': False,
                'blinks': 0
            })
        
        return JsonResponse({
            'ear': f"{camera_instance.current_ear:.2f}",
            'focus': camera_instance.current_focus,
            'face_detected': camera_instance.face_detected,
            'blinks': camera_instance.blink_count
        })

import cv2
import numpy as np
from .models import MonitorSession, BlinkEvent, AlertEvent
from math import hypot
import mediapipe as mp
#import base64 AL FINAL NO LO USE
import threading
import time
from math import hypot
from django.utils import timezone

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
last_avg_distance = 0.0
last_avg_ear = 0.0

# ============================================================================
# CONFIGURACIÓN MEJORADA PARA DETECCIÓN DE PARPADEOS
# ============================================================================

# Configuración de detección por distancia de párpados
VERTICAL_DISTANCE_THRESHOLD = 5  # Pixeles - cuando es menor, ojos cerrados
EAR_THRESHOLD = 0.20  # Umbral EAR como respaldo
MIN_BLINK_DURATION = 0.01  # 50ms mínimo
MAX_BLINK_DURATION = 0.35  # 350ms máximo
DEBOUNCE_TIME = 0.15  # 150ms entre parpadeos

# Estados del parpadeo
class BlinkState:
    OPEN = "ABIERTO"
    CLOSING = "CERRANDO"
    CLOSED = "CERRADO"
    OPENING = "ABRIENDO"

# Variables globales para tracking de parpadeos
blink_state = BlinkState.OPEN
blink_start_time = None
last_blink_time = 0
blink_counter = 0

def calculate_ear(eye_points):
    """
    Calcula Eye Aspect Ratio (EAR) - método tradicional como respaldo
    """
    try:
        points = np.array(eye_points, dtype=np.float32)
        
        # Distancias verticales
        A = hypot(points[1][0] - points[5][0], points[1][1] - points[5][1])
        B = hypot(points[2][0] - points[4][0], points[2][1] - points[4][1])
        
        # Distancia horizontal
        C = hypot(points[0][0] - points[3][0], points[0][1] - points[3][1])
        
        if C < 1e-3:
            return None
            
        ear = (A + B) / (2.0 * C)
        return ear if 0.05 <= ear <= 0.6 else None
    except Exception:
        return None

def calculate_vertical_distance(eye_points):
    """
    Calcula la distancia vertical promedio entre párpado superior e inferior.
    Más preciso que EAR para detectar el contacto real de los párpados.
    
    eye_points: [outer_corner, top1, top2, inner_corner, bottom2, bottom1]
    """
    try:
        points = np.array(eye_points, dtype=np.float32)
        
        # Calcular distancias verticales en múltiples puntos
        # top1 <-> bottom1 (punto medio-exterior)
        d1 = abs(points[1][1] - points[5][1])
        
        # top2 <-> bottom2 (punto medio-interior)
        d2 = abs(points[2][1] - points[4][1])
        
        # Promedio de las distancias verticales
        avg_vertical_distance = (d1 + d2) / 2.0
        
        return avg_vertical_distance
    except Exception:
        return None

def are_eyes_closed(left_eye_points, right_eye_points):
    """
    Determina si los ojos están cerrados basándose en:
    1. Distancia vertical de los párpados (principal)
    2. EAR como validación secundaria
    """
    # Calcular distancias verticales
    left_dist = calculate_vertical_distance(left_eye_points)
    right_dist = calculate_vertical_distance(right_eye_points)
    
    if left_dist is None or right_dist is None:
        return False, None, None
    
    # Promedio de ambos ojos
    avg_distance = (left_dist + right_dist) / 2.0
    
    # Criterio principal: distancia vertical muy pequeña = ojos cerrados
    if avg_distance < VERTICAL_DISTANCE_THRESHOLD:
        return True, avg_distance, None
    
    # Validación secundaria con EAR
    left_ear = calculate_ear(left_eye_points)
    right_ear = calculate_ear(right_eye_points)
    
    if left_ear is not None and right_ear is not None:
        avg_ear = (left_ear + right_ear) / 2.0
        if avg_ear < EAR_THRESHOLD:
            return True, avg_distance, avg_ear
    
    return False, avg_distance, None

def detect_blink_improved(left_eye_points, right_eye_points):
    """
    Detecta parpadeos usando máquina de estados y detección de contacto de párpados.
    Retorna: (blink_detected, current_state, debug_info)
    """
    global blink_state, blink_start_time, last_blink_time, blink_counter
    
    current_time = time.time()
    eyes_closed, avg_distance, avg_ear = are_eyes_closed(left_eye_points, right_eye_points)
    blink_detected = False
    
    # Calcular métricas para debug
    left_dist = calculate_vertical_distance(left_eye_points)
    right_dist = calculate_vertical_distance(right_eye_points)
    left_ear = calculate_ear(left_eye_points)
    right_ear = calculate_ear(right_eye_points)
    
    debug_info = {
        'left_distance': left_dist,
        'right_distance': right_dist,
        'avg_distance': avg_distance if avg_distance else 0,
        'left_ear': left_ear,
        'right_ear': right_ear,
        'avg_ear': (left_ear + right_ear) / 2.0 if left_ear and right_ear else 0,
        'eyes_closed': eyes_closed,
        'state': blink_state
    }
    
    # Máquina de estados para parpadeo
    if blink_state == BlinkState.OPEN:
        if eyes_closed:
            # Iniciar posible parpadeo
            blink_state = BlinkState.CLOSING
            blink_start_time = current_time
            
    elif blink_state == BlinkState.CLOSING:
        if eyes_closed:
            # Continuar cerrado
            blink_state = BlinkState.CLOSED
        else:
            # Se abrió muy rápido, fue ruido
            blink_state = BlinkState.OPEN
            blink_start_time = None
            
    elif blink_state == BlinkState.CLOSED:
        if not eyes_closed:
            # Comenzar apertura
            blink_state = BlinkState.OPENING
            
    elif blink_state == BlinkState.OPENING:
        if not eyes_closed:
            # Parpadeo completado
            blink_duration = current_time - blink_start_time if blink_start_time else 0
            time_since_last = current_time - last_blink_time
            
            # Validar duración y debounce
            if (MIN_BLINK_DURATION <= blink_duration <= MAX_BLINK_DURATION and 
                time_since_last >= DEBOUNCE_TIME):
                blink_detected = True
                blink_counter += 1
                last_blink_time = current_time
                debug_info['blink_duration'] = blink_duration
            
            # Resetear estado
            blink_state = BlinkState.OPEN
            blink_start_time = None
        else:
            # Volvió a cerrar, mantener en CLOSED
            blink_state = BlinkState.CLOSED
    
    return blink_detected, blink_state, debug_info

def reset_blink_counter():
    """Resetear el contador de parpadeos"""
    global blink_counter, blink_state, blink_start_time, last_blink_time
    blink_counter = 0
    blink_state = BlinkState.OPEN
    blink_start_time = None
    last_blink_time = 0

def draw_eye_landmarks(frame, left_eye_points, right_eye_points, debug_info, blink_detected, blink_counter):
    """
    Dibuja landmarks de los ojos y panel de información mejorado
    """
    output = frame.copy()
    height, width = frame.shape[:2]

    # Panel de información inferior
    info_panel_height = 200
    info_panel_y = height - info_panel_height
    overlay = output.copy()
    cv2.rectangle(overlay, (0, info_panel_y), (width, height), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.4, output, 0.6, 0, output)

    def draw_eye(points, is_left):
        """Dibuja landmarks del ojo con colores según estado"""
        if len(points) == 6:
            pts = np.array(points, dtype=np.int32)
            
            # Color según si está parpadeando
            if blink_detected:
                color = (0, 0, 255)  # Rojo = parpadeo
            elif debug_info.get('eyes_closed', False):
                color = (0, 165, 255)  # Naranja = cerrando
            else:
                color = (0, 255, 0)  # Verde = abierto
            
            # Dibujar contorno del ojo
            cv2.polylines(output, [pts], True, color, 2)
            cv2.polylines(output, [pts], True, (255, 255, 255), 1)
            
            # Dibujar puntos clave
            for i, p in enumerate(pts):
                cv2.circle(output, tuple(p), 3, (0, 165, 255), -1)
                cv2.circle(output, tuple(p), 1, (255, 255, 255), -1)

    # Dibujar ambos ojos
    draw_eye(left_eye_points, True)
    draw_eye(right_eye_points, False)

    # Panel de métricas
    info_x = 18
    info_y = info_panel_y + 28
    
    # Título del panel con color según estado
    if blink_detected:
        title_bg_color = (0, 0, 255)  # Rojo
        title_text = "¡PARPADEO DETECTADO!"
    elif debug_info.get('state') == BlinkState.CLOSED:
        title_bg_color = (0, 165, 255)  # Naranja
        title_text = "OJOS CERRADOS"
    else:
        title_bg_color = (0, 128, 0)  # Verde
        title_text = "MONITOREANDO"
    
    cv2.rectangle(output, (10, info_y - 20), (280, info_y), title_bg_color, -1)
    cv2.putText(output, title_text, (15, info_y - 5), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,255,255), 2)

    # Métricas principales
    y_offset = info_y + 30
    
    # Distancia vertical (métrica principal)
    avg_dist = debug_info.get('avg_distance', 0)
    dist_text = f"{avg_dist:.2f}px" if avg_dist else "--"
    dist_color = (0, 0, 255) if avg_dist < VERTICAL_DISTANCE_THRESHOLD else (0, 255, 0)
    cv2.putText(output, f"Dist. Vertical: {dist_text}", 
                (info_x, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.6, dist_color, 2)
    
    # EAR (métrica secundaria)
    y_offset += 30
    avg_ear = debug_info.get('avg_ear', 0)
    ear_text = f"{avg_ear:.3f}" if avg_ear else "--"
    cv2.putText(output, f"EAR: {ear_text}", 
                (info_x, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,255), 2)
    
    # Estado actual
    y_offset += 30
    state = debug_info.get('state', 'N/A')
    state_color = (0, 0, 255) if blink_detected else (255, 255, 255)
    cv2.putText(output, f"Estado: {state}", 
                (info_x, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.6, state_color, 2)
    
    # Contador de parpadeos
    y_offset += 30
    cv2.putText(output, f"Parpadeos: {blink_counter}", 
                (info_x, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
    
    # Umbral de detección (referencia)
    y_offset += 28
    cv2.putText(output, f"Umbral: {VERTICAL_DISTANCE_THRESHOLD:.1f}px", 
                (info_x, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (150, 150, 150), 1)

    return output

def generate_frames():
    """
    Genera frames del video con detección mejorada de parpadeos
    """
    global webcam_global, streaming_active, current_session_id
    global last_faces_count, last_eyes_count, last_avg_distance, last_avg_ear
    global blink_counter

    print("=== GENERATE_FRAMES INICIADO (DETECCIÓN MEJORADA V2) ===")
    
    # Resetear contador al inicio
    reset_blink_counter()
    frame_count = 0

    # Inicializar webcam si no está abierta
    with webcam_lock:
        if webcam_global is None:
            webcam_global = cv2.VideoCapture(0)
            webcam_global.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            webcam_global.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            webcam_global.set(cv2.CAP_PROP_FPS, 30)
        cap = webcam_global

    # Crear FaceMesh en contexto local
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
                
                # Leer frame
                with webcam_lock:
                    if cap is None or not cap.isOpened():
                        print("Webcam no disponible")
                        break
                    ret, frame = cap.read()
                
                if not ret:
                    print("No se pudo leer frame")
                    break

                # Procesar frame
                frame = cv2.flip(frame, 1)
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                
                # Detección de rostro
                results = None
                try:
                    results = face_mesh_local.process(frame_rgb)
                except Exception as e:
                    print(f"MediaPipe error: {e}")
                    results = None

                # Variables para este frame
                blink_detected = False
                faces_count = 0
                left_eye_points = []
                right_eye_points = []
                debug_info = {}

                if results and results.multi_face_landmarks:
                    faces_count = len(results.multi_face_landmarks)
                    face_landmarks = results.multi_face_landmarks[0]
                    h, w = frame.shape[:2]
                    
                    # Extraer puntos de los ojos
                    for idx in LEFT_EYE:
                        lm = face_landmarks.landmark[idx]
                        left_eye_points.append([int(lm.x * w), int(lm.y * h)])
                    
                    for idx in RIGHT_EYE:
                        lm = face_landmarks.landmark[idx]
                        right_eye_points.append([int(lm.x * w), int(lm.y * h)])
                    
                    # Detectar parpadeo con el método mejorado
                    if len(left_eye_points) == 6 and len(right_eye_points) == 6:
                        blink_detected, state, debug_info = detect_blink_improved(
                            left_eye_points, 
                            right_eye_points
                        )
                        
                        # Si se detectó un parpadeo, guardarlo en BD
                        if blink_detected:
                            print(f"✓ PARPADEO #{blink_counter} detectado!")
                            print(f"  Distancia: {debug_info.get('avg_distance', 0):.2f}px")
                            print(f"  Duración: {debug_info.get('blink_duration', 0):.3f}s")
                            
                            if current_session_id is not None:
                                try:
                                    session = MonitorSession.objects.get(id=current_session_id)
                                    BlinkEvent.objects.create(
                                        session=session,
                                        timestamp=timezone.now(),
                                        duration_ms=int(debug_info.get('blink_duration', 0) * 1000)
                                    )
                                except Exception as e:
                                    print(f"[WARN] No se pudo guardar BlinkEvent: {e}")
                            
                            # Alerta de fatiga cada 30 parpadeos (ajustar según necesidad)
                            if blink_counter > 0 and blink_counter % 30 == 0:
                                if current_session_id is not None:
                                    try:
                                        session = MonitorSession.objects.get(id=current_session_id)
                                        # Sanitizar metadata para evitar tipos no serializables (numpy.float32)
                                        try:
                                            metadata = {
                                                'blink_counter': int(blink_counter),
                                                'avg_distance': float(debug_info.get('avg_distance', 0) or 0.0)
                                            }
                                        except Exception:
                                            metadata = {'blink_counter': int(blink_counter), 'avg_distance': float(0.0)}

                                        AlertEvent.objects.create(
                                            session=session,
                                            alert_type=AlertEvent.ALERT_FATIGUE,
                                            triggered_at=timezone.now(),
                                            metadata=metadata
                                        )
                                        print(f"[ALERT] ⚠ Alerta de fatiga #{blink_counter // 30}")
                                    except Exception as e:
                                        print(f"[WARN] No se pudo guardar AlertEvent: {e}")

                # Actualizar métricas globales para API (asegurar tipos nativos)
                last_faces_count = int(faces_count)
                last_eyes_count = 2 if faces_count > 0 else 0
                if debug_info:
                    try:
                        last_avg_distance = float(debug_info.get('avg_distance', last_avg_distance) or last_avg_distance)
                    except Exception:
                        # mantener valor previo si falla la conversión
                        pass
                    try:
                        last_avg_ear = float(debug_info.get('avg_ear', last_avg_ear) or last_avg_ear)
                    except Exception:
                        pass

                # Actualizar sesión en BD
                if current_session_id is not None:
                    try:
                        session = MonitorSession.objects.get(id=current_session_id)
                        if debug_info.get('avg_distance'):
                            # Guardar distancia vertical como métrica principal
                            session.avg_ear = float(debug_info['avg_distance'])
                        session.total_blinks = blink_counter
                        session.save(update_fields=["avg_ear", "total_blinks"])
                    except Exception as e:
                        print(f"[WARN] No actualizar sesión: {e}")
                
                current_time = time.time()
                        
                # === 1. ALERTA DE ILUMINACIÓN BAJA ===
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                brightness = np.mean(gray)
                if brightness < 40:
                    if not hasattr(generate_frames, "low_light_start") or generate_frames.low_light_start is None:
                        generate_frames.low_light_start = current_time
                    elif current_time - generate_frames.low_light_start >= 3.0:
                        if current_session_id is not None:
                            try:
                                session = MonitorSession.objects.get(id=current_session_id)
                                AlertEvent.objects.create(
                                    session=session,
                                    alert_type=AlertEvent.ALERT_LOW_LIGHT,
                                    triggered_at=timezone.now(),
                                    metadata={"brightness": float(brightness)}
                                )
                                print("[ALERT] ⚠ Iluminación baja detectada")
                            except Exception as e:
                                print(f"[WARN] No se pudo guardar alerta LOW_LIGHT: {e}")
                        generate_frames.low_light_start = None
                else:
                    generate_frames.low_light_start = None


                # === 2. ALERTA DE DISTRACCIÓN PROLONGADA ===
                if faces_count == 0:
                    if not hasattr(generate_frames, "no_face_start") or generate_frames.no_face_start is None:
                        generate_frames.no_face_start = current_time
                    elif current_time - generate_frames.no_face_start >= 5.0:
                        if current_session_id is not None:
                            try:
                                session = MonitorSession.objects.get(id=current_session_id)
                                AlertEvent.objects.create(
                                    session=session,
                                    alert_type=AlertEvent.ALERT_DISTRACT,
                                    triggered_at=timezone.now(),
                                    metadata={"no_face_duration_s": round(current_time - generate_frames.no_face_start, 2)}
                                )
                                print("[ALERT] ⚠ Distracción prolongada detectada")
                            except Exception as e:
                                print(f"[WARN] No se pudo guardar alerta DISTRACT: {e}")
                        generate_frames.no_face_start = None
                else:
                    generate_frames.no_face_start = None


                # === 3. ALERTA DE CÁMARA PERDIDA ===
                if not ret:
                    print("No se pudo leer frame")

                    if not hasattr(generate_frames, "no_frame_start") or generate_frames.no_frame_start is None:
                        generate_frames.no_frame_start = current_time
                    elif current_time - generate_frames.no_frame_start >= 3.0:
                        if current_session_id is not None:
                            try:
                                session = MonitorSession.objects.get(id=current_session_id)
                                AlertEvent.objects.create(
                                    session=session,
                                    alert_type=AlertEvent.ALERT_CAMERA_LOST,
                                    triggered_at=timezone.now(),
                                    metadata={"duration_sin_frame": round(current_time - generate_frames.no_frame_start, 2)}
                                )
                                print("[ALERT] ⚠ Cámara perdida")
                            except Exception as e:
                                print(f"[WARN] No se pudo guardar alerta CAMERA_LOST: {e}")
                        generate_frames.no_frame_start = None

                    time.sleep(0.1)
                    continue
                else:
                    generate_frames.no_frame_start = None



                # Dibujar visualización
                frame_out = draw_eye_landmarks(
                    frame, 
                    left_eye_points, 
                    right_eye_points,
                    debug_info,
                    blink_detected, 
                    blink_counter
                )

                # Codificar y enviar frame
                encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), 80]
                success, buffer = cv2.imencode('.jpg', frame_out, encode_params)
                
                if not success:
                    continue
                
                frame_bytes = buffer.tobytes()
                
                try:
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
                except GeneratorExit:
                    break

    except Exception as e:
        print(f"Error crítico en generate_frames: {e}")
    finally:
        # Cleanup
        with webcam_lock:
            if webcam_global is not None:
                try:
                    webcam_global.release()
                except Exception:
                    pass
                webcam_global = None
        print(f"=== GENERATE_FRAMES TERMINADO (Total parpadeos: {blink_counter}) ===")


# ============================================================================
# VISTAS DE TEMPLATE Y END POINTS DE API
# ============================================================================

@method_decorator(login_required, name='dispatch')
class ModuloTemplateView(TemplateView):
    template_name = 'monitoring/home.html'

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
            s.alert_count = s.alerts.count()
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
'''
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
'''

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
@csrf_exempt
@require_http_methods(["POST"])
def pause_monitoring(request):
    """Pausa la sesión de monitoreo actual"""
    global camera_instance, current_session_id, blink_counter

    with camera_lock:
        if not camera_instance or not camera_instance.is_running:
            return JsonResponse({
                'status': 'error',
                'message': 'No hay sesión activa que pausar',
                'is_paused': False,
                'blink_count': 0
            }, status=400)

        try:
            session = MonitorSession.objects.get(id=current_session_id)
            
            # Verificar el estado actual de pausa
            existing_pause = session.pauses.filter(resume_time__isnull=True).first()
            
            # Si ya está pausada, mantener consistencia
            if existing_pause:
                with camera_instance._internal_lock:
                    if not camera_instance.is_paused:
                        camera_instance.is_paused = True
                        
                return JsonResponse({
                    'status': 'success',
                    'message': 'La sesión está pausada',
                    'is_paused': True,
                    'blink_count': blink_counter,
                    'session_id': current_session_id
                })

            # Crear nuevo registro de pausa
            pause = SessionPause.objects.create(
                session=session,
                pause_time=timezone.now()
            )
            
            # Guardar métricas actuales
            with camera_instance._internal_lock:
                current_blinks = blink_counter
                camera_instance.is_paused = True
                session.total_blinks = current_blinks
                session.save(update_fields=['total_blinks'])
            
            print(f"[PAUSE] Sesión {session.id} pausada. Parpadeos: {current_blinks}")
            
            return JsonResponse({
                'status': 'success',
                'message': 'Monitoreo pausado correctamente',
                'is_paused': True,
                'blink_count': current_blinks,
                'session_id': current_session_id,
                'timestamp': timezone.now().isoformat()
            })
            
        except MonitorSession.DoesNotExist:
            return JsonResponse({
                'status': 'error',
                'message': 'Sesión no encontrada',
                'is_paused': False,
                'blink_count': 0
            }, status=404)
        except Exception as e:
            print(f"[ERROR] Error al pausar sesión: {str(e)}")
            return JsonResponse({
                'status': 'error',
                'message': f'Error al pausar: {str(e)}',
                'is_paused': False,
                'blink_count': blink_counter
            }, status=500)

@login_required
@csrf_exempt
@require_http_methods(["POST"])
def resume_monitoring(request):
    """Reanuda la sesión de monitoreo actual"""
    global camera_instance, current_session_id, blink_counter

    with camera_lock:
        if not camera_instance or not camera_instance.is_running:
            return JsonResponse({
                'status': 'error',
                'message': 'No hay sesión activa que reanudar',
                'is_paused': True,
                'blink_count': 0
            }, status=400)

        try:
            session = MonitorSession.objects.get(id=current_session_id)
            
            # Verificar el estado actual de pausa
            current_pause = session.pauses.filter(resume_time__isnull=True).last()
            
            # Si no está pausada, mantener consistencia
            if not current_pause:
                with camera_instance._internal_lock:
                    if camera_instance.is_paused:
                        camera_instance.is_paused = False
                        
                return JsonResponse({
                    'status': 'success',
                    'message': 'La sesión está activa',
                    'is_paused': False,
                    'blink_count': blink_counter,
                    'session_id': current_session_id
                })
            
            # Obtener timestamp actual
            resume_time = timezone.now()
            
            with camera_instance._internal_lock:
                # Preservar el contador actual de parpadeos
                current_blinks = blink_counter
                
                try:
                    # Reinicializar la captura de video
                    if camera_instance.video and camera_instance.video.isOpened():
                        camera_instance.video.release()
                    
                    camera_instance.video = cv2.VideoCapture(0)
                    camera_instance.video.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                    camera_instance.video.set(cv2.CAP_PROP_FPS, 30)
                    
                    if not camera_instance.video.isOpened():
                        raise Exception("No se pudo reiniciar la cámara")
                    
                    # Limpiar frames de pausa
                    camera_instance.pause_frame = None
                    camera_instance.pause_metrics = None
                    camera_instance.is_paused = False
                    
                    # Restaurar el contador de parpadeos
                    blink_counter = current_blinks
                    
                    # Actualizar el registro de pausa
                    current_pause.resume_time = resume_time
                    current_pause.save()
                    
                    print(f"[RESUME] Sesión {session.id} reanudada. Parpadeos: {current_blinks}")
                    
                except Exception as cam_error:
                    print(f"[ERROR] Error al reiniciar cámara: {str(cam_error)}")
                    raise Exception(f"Error al reiniciar cámara: {str(cam_error)}")
            
            return JsonResponse({
                'status': 'success',
                'message': 'Monitoreo reanudado correctamente',
                'is_paused': False,
                'blink_count': current_blinks,
                'session_id': current_session_id,
                'timestamp': resume_time.isoformat()
            })
            
        except MonitorSession.DoesNotExist:
            return JsonResponse({
                'status': 'error',
                'message': 'Sesión no encontrada',
                'is_paused': True,
                'blink_count': 0
            }, status=404)
        except Exception as e:
            print(f"[ERROR] Error al reanudar sesión: {str(e)}")
            return JsonResponse({
                'status': 'error',
                'message': f'Error al reanudar: {str(e)}',
                'is_paused': True,
                'blink_count': blink_counter
            }, status=500)

@login_required
def session_metrics(request):
    """Return current session metrics as JSON for live updates"""
    global current_session_id

    if current_session_id is None:
        # Convertir a tipos primitivos para Json
        return JsonResponse({
            'status': 'no_session',
            'message': 'No active monitoring session',
            'avg_distance': float(0.0),
            'avg_ear': float(0.0),
            'total_blinks': int(0),
            'faces': int(last_faces_count),
            'eyes': int(last_eyes_count),
            'debug_distance': float(last_avg_distance or 0.0),
            'debug_ear': float(last_avg_ear or 0.0)
        })

    try:
        session = MonitorSession.objects.get(id=current_session_id)
        # Asegurar tipos serializables
        return JsonResponse({
            'status': 'success',
            'avg_distance': float(last_avg_distance or 0.0),
            'avg_ear': float(last_avg_ear or 0.0),
            'total_blinks': int(session.total_blinks or 0),
            'faces': int(last_faces_count),
            'eyes': int(last_eyes_count),
            'blink_state': str(blink_state)
        })
    except MonitorSession.DoesNotExist:
        return JsonResponse({
            'status': 'error',
            'message': 'Session not found',
            'avg_distance': float(0.0),
            'avg_ear': float(0.0),
            'total_blinks': int(0),
            'faces': int(last_faces_count),
            'eyes': int(last_eyes_count)
        })

@login_required
@require_http_methods(["POST"])
def start_webcam_test(request):
    """Iniciar webcam y crear una nueva sesión de monitoreo"""
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
            metadata={'detection_method': 'vertical_distance'}
        )
        current_session_id = session.id
        
        # Inicializar cache
        cache.set(f'monitor:{session.id}:blink_count', 0, timeout=3600)
        
        # Resetear contador
        reset_blink_counter()
        
        streaming_active = True
        
        print(f"✓ Sesión creada: {session.id}")
        print(f"✓ Método de detección: Distancia vertical de párpados")
        print(f"✓ Umbral: {VERTICAL_DISTANCE_THRESHOLD}px")
        
        return JsonResponse({
            'status': 'success',
            'message': 'Webcam iniciada y sesión creada',
            'session_id': session.id,
            'detection_method': 'vertical_distance',
            'threshold': VERTICAL_DISTANCE_THRESHOLD
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
    """Detener webcam y finalizar sesión de monitoreo"""
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
            
            print(f"✓ Sesión finalizada: {session.id}")
            print(f"✓ Total de parpadeos detectados: {blink_counter}")
            print(f"✓ Duración: {session.duration_seconds}s")
            
            session_id = session.id
            duration = session.duration_seconds
            total_blinks = blink_counter
        except MonitorSession.DoesNotExist:
            session_id = None
            duration = 0
            total_blinks = 0
    else:
        session_id = None
        duration = 0
        total_blinks = 0
    
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
        'duration_seconds': duration,
        'total_blinks': total_blinks
    })
