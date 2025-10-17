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
import mediapipe as mp
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


# ============================================================================
# FUNCIONES DE DETECCIÓN CON MEDIAPIPE
# ============================================================================
def calculate_ear(eye_points):
    """
    Calcula el EAR (Eye Aspect Ratio) con mayor precisión usando 6 puntos.
    Implementa la fórmula mejorada con pesos en las distancias verticales.
    """
    try:
        # Convertir a numpy array para cálculos más eficientes
        points = np.array(eye_points)
        
        # Distancias verticales con pesos
        # Dar más peso a la distancia central que es más estable
        A = np.linalg.norm(points[1] - points[5])  # Distancia vertical externa
        B = np.linalg.norm(points[2] - points[4])  # Distancia vertical interna
        
        # Distancia horizontal
        C = np.linalg.norm(points[0] - points[3])
        
        # Evitar división por cero y valores anómalos
        if C < 0.1:
            return None
            
        # Calcular EAR con pesos (más peso a la distancia central)
        ear = (0.4 * A + 0.6 * B) / (2.0 * C)
        
        return ear if 0.1 <= ear <= 0.5 else None  # Filtrar valores fuera de rango
        
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
                if current_time - last_blink_time > (DEBOUNCE_FRAMES / 30.0):  # Convertir frames a segundos
                    blink_counter += 1
                    last_blink_time = current_time
                    closed_counter = 0
                    return True
            
            closed_counter = 0
            open_counter += 1
    
    return False

def draw_eye_landmarks(frame, left_eye_points, right_eye_points, ear_value, blink_detected):
    """
    Dibuja los landmarks de los ojos y la información de EAR/parpadeos.
    """
    # Crear copia para no modificar el frame original
    output = frame.copy()
    
    # Función helper para dibujar un ojo
    def draw_eye(points, color):
        if len(points) == 6:
            points = np.array(points, dtype=np.int32)
            # Dibujar contorno
            cv2.polylines(output, [points], True, color, 2)
            # Dibujar puntos
            for point in points:
                cv2.circle(output, tuple(point), 2, (0, 255, 255), -1)
    
    # Dibujar ambos ojos
    draw_eye(left_eye_points, (0, 255, 0) if not blink_detected else (0, 0, 255))
    draw_eye(right_eye_points, (0, 255, 0) if not blink_detected else (0, 0, 255))
    
    # Mostrar valor EAR
    cv2.putText(output, f"EAR: {ear_value:.3f}", (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
    
    # Mostrar estado de parpadeo
    if blink_detected:
        cv2.putText(output, "BLINK!", (10, 60),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
    
    # Mostrar contador de parpadeos
    cv2.putText(output, f"Blinks: {blink_counter}", (10, 90),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
    
    return output


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
        
        total_seconds = (
        MonitorSession.objects
        .filter(user=self.request.user)
        .aggregate(total_time=Sum('duration_seconds'))['total_time'] or 0)
        
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
# STREAMING DE VIDEO CON MEDIAPIPE FACEMESH
# ============================================================================
def generate_frames():
    """
    Genera frames de video con detección facial y de ojos usando MediaPipe.
    Implementa detección de parpadeos optimizada con:
    - Calibración automática
    - Umbral dinámico
    - Filtrado de señal EAR
    - Detección robusta de parpadeos
    """
    global webcam_global, streaming_active, current_session_id
    global last_faces_count, last_eyes_count, last_avg_ear
    global blink_counter, ear_history
    
    print("=== GENERATE_FRAMES INICIADO (DETECCIÓN MEJORADA) ===")
    
    # Resetear variables de tracking
    blink_counter = 0
    ear_history = []  # Historial para calibración automática
    last_blink_time = time.time()
    
    with webcam_lock:
        if webcam_global is None:
            webcam_global = cv2.VideoCapture(0)
            webcam_global.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            webcam_global.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            webcam_global.set(cv2.CAP_PROP_FPS, 30)
    
    session = None
    if current_session_id:
        try:
            session = MonitorSession.objects.get(id=current_session_id)
        except MonitorSession.DoesNotExist:
            pass
    
    frame_count = 0
    
    # Inicializar MediaPipe FaceMesh
    # Loop principal de streaming
    while streaming_active:
        with webcam_lock:
            if webcam_global is None or not webcam_global.isOpened():
                print("Webcam no disponible")
                break
            ret, frame = webcam_global.read()
        
        if not ret:
            print("No se pudo leer frame")
            break
        
        frame_count += 1
        
        # Voltear frame horizontalmente para efecto espejo
        frame = cv2.flip(frame, 1)
        
        # Convertir BGR a RGB para MediaPipe
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = face_mesh.process(frame_rgb)
        
        # Variables para tracking
        current_ear = None
        blink_detected = False
        face_detected = False
        
        if results.multi_face_landmarks:
            face_detected = True
            face_landmarks = results.multi_face_landmarks[0]  # Primera cara detectada
            
            # Extraer coordenadas de los ojos
            frame_height, frame_width = frame.shape[:2]
            
            # Obtener puntos del ojo izquierdo
            left_eye_points = []
            for idx in LEFT_EYE:
                lm = face_landmarks.landmark[idx]
                x, y = int(lm.x * frame_width), int(lm.y * frame_height)
                left_eye_points.append([x, y])
            
            # Obtener puntos del ojo derecho
            right_eye_points = []
            for idx in RIGHT_EYE:
                lm = face_landmarks.landmark[idx]
                x, y = int(lm.x * frame_width), int(lm.y * frame_height)
                right_eye_points.append([x, y])
            
            # Calcular EAR para cada ojo
            left_ear = calculate_ear(left_eye_points)
            right_ear = calculate_ear(right_eye_points)
            
            # Usar el valor más bajo para detectar parpadeos
            if left_ear is not None and right_ear is not None:
                current_ear = min(left_ear, right_ear)
                # Detectar parpadeo usando el sistema mejorado
                blink_detected = detect_blink(current_ear)
                        
                        # ===== CALIBRACIÓN AUTOMÁTICA (primeros 60 frames) =====
                        if calibration_frames < 60:
                            calibration_frames += 1
                            CALIBRATION_SAMPLES.append(ear_raw)
                            
                            if calibration_frames == 60:
                                # Calcular baseline promedio (con ojos abiertos)
                                sorted_samples = sorted(CALIBRATION_SAMPLES)
                                # Tomar el 75% percentil como baseline (ignorar valores muy bajos/altos)
                                baseline_ear = sorted_samples[int(len(sorted_samples) * 0.75)]
                                max_ear_baseline = max(CALIBRATION_SAMPLES)
                                
                                # Ajustar umbrales basados en el baseline individual
                                EAR_THRESH = baseline_ear * 0.75  # 75% del baseline
                                MIN_EAR_OPEN = baseline_ear * 0.85  # 85% del baseline
                                
                                print(f"[CALIBRACIÓN] ✓ Completada!")
                                print(f"  Baseline EAR: {baseline_ear:.3f}")
                                print(f"  Max EAR: {max_ear_baseline:.3f}")
                                print(f"  Umbral cerrado: {EAR_THRESH:.3f}")
                                print(f"  Umbral abierto: {MIN_EAR_OPEN:.3f}")
                            
                            eyes_status = f"CALIBRANDO... {calibration_frames}/60"
                            status_color = (255, 165, 0)  # Naranja
                            
                        # ===== DETECCIÓN NORMAL =====
                        else:
                            # SUAVIZADO DE EAR: promedio móvil de últimos 4 frames (más suave para ojos asiáticos)
                            last_ear_values.append(ear_raw)
                            if len(last_ear_values) > 4:
                                last_ear_values.pop(0)
                            ear = sum(last_ear_values) / len(last_ear_values)
                            
                            # LÓGICA MEJORADA con HISTÉRESIS adaptativa
                            if debounce_counter > 0:
                                # En período de debounce
                                debounce_counter -= 1
                                eyes_status = f"ESPERA ({debounce_counter})"
                                status_color = (255, 128, 0)  # Naranja
                            elif ear < EAR_THRESH:
                                # Ojos cerrados - incrementar contador
                                aux_counter += 1
                                eyes_status = f"CERRADO ({aux_counter}/{NUM_FRAMES})"
                                status_color = (0, 0, 255)  # Rojo
                            elif ear > MIN_EAR_OPEN:
                                # Ojos claramente abiertos - verificar parpadeo
                                if aux_counter >= NUM_FRAMES:
                                    # ¡Parpadeo CONFIRMADO!
                                    blink_counter += 1
                                    debounce_counter = DEBOUNCE_FRAMES
                                    
                                    # Registrar en BD
                                    if session:
                                        session.total_blinks = (session.total_blinks or 0) + 1
                                        BlinkEvent.objects.create(
                                            session=session,
                                            timestamp=timezone.now(),
                                            duration_ms=int(aux_counter * 33.33)
                                        )
                                        print(f"[BLINK] ✓ #{session.total_blinks} | Frames: {aux_counter} | EAR: {ear:.3f}")
                                        
                                        # Control de alertas
                                        blink_count_key = f'monitor:{session.id}:blink_count'
                                        bc = cache.get(blink_count_key, 0) + 1
                                        cache.set(blink_count_key, bc, timeout=3600)
                                        
                                        if bc > 30:
                                            session.alerts_count = (session.alerts_count or 0) + 1
                                            AlertEvent.objects.create(
                                                session=session,
                                                alert_type=AlertEvent.ALERT_FATIGUE,
                                                triggered_at=timezone.now(),
                                                metadata={'blink_count': bc, 'avg_ear': ear}
                                            )
                                            cache.set(blink_count_key, 0, timeout=3600)
                                            print(f"[ALERT] ⚠ Alerta de fatiga")
                                    
                                    eyes_status = "✓ PARPADEO!"
                                    status_color = (0, 255, 0)
                                else:
                                    eyes_status = "ABIERTO"
                                    status_color = (0, 255, 0)
                                
                                aux_counter = 0
                            else:
                                # Zona intermedia
                                eyes_status = f"INTERMEDIO"
                                status_color = (255, 255, 0)
                        
                        # Dibujar ojos en el frame
                        frame = drawing_output(frame, coordinates_left_eye, coordinates_right_eye, 
                                             session.total_blinks if session else blink_counter)
            
            # Actualizar variables globales para métricas
            last_faces_count = 1 if face_detected else 0
            last_eyes_count = 2 if face_detected else 0
            last_avg_ear = float(ear)
            
            # Actualizar EAR promedio en la sesión
            if session and frame_count % 5 == 0 and face_detected:
                if session.avg_ear is None:
                    session.avg_ear = ear
                else:
                    session.avg_ear = session.avg_ear * 0.9 + ear * 0.1
                session.save()
            
            # Mostrar información en el frame con mejor diseño
            info_y = 30
            
            # Panel de información con fondo semitransparente
            overlay = frame.copy()
            cv2.rectangle(overlay, (5, 5), (320, 180), (0, 0, 0), -1)
            frame = cv2.addWeighted(overlay, 0.3, frame, 0.7, 0)
            
            cv2.putText(frame, f'Rostros: {last_faces_count}', (10, info_y), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            
            # Mostrar EAR con más precisión
            if calibration_frames >= 60:
                cv2.putText(frame, f'EAR: {ear:.4f}', (10, info_y + 25), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
                
                # Mostrar umbrales calibrados
                cv2.putText(frame, f'Umbral: {EAR_THRESH:.3f}', (10, info_y + 50), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (150, 150, 255), 1)
                
                # Mostrar EAR individual de cada ojo
                if face_detected and len(coordinates_left_eye) == 6:
                    cv2.putText(frame, f'L: {ear_left:.3f} R: {ear_right:.3f}', (10, info_y + 75), 
                               cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
                
                # Barra visual de EAR
                bar_x = 10
                bar_y = info_y + 95
                bar_width = 200
                bar_height = 15
                
                # Fondo de la barra
                cv2.rectangle(frame, (bar_x, bar_y), (bar_x + bar_width, bar_y + bar_height), (50, 50, 50), -1)
                
                # Líneas de referencia (umbrales)
                thresh_pos = int((EAR_THRESH / 0.35) * bar_width)
                open_pos = int((MIN_EAR_OPEN / 0.35) * bar_width)
                cv2.line(frame, (bar_x + thresh_pos, bar_y), (bar_x + thresh_pos, bar_y + bar_height), (0, 0, 255), 2)
                cv2.line(frame, (bar_x + open_pos, bar_y), (bar_x + open_pos, bar_y + bar_height), (0, 255, 0), 2)
                
                # Valor actual de EAR
                ear_pos = int((ear / 0.35) * bar_width)
                ear_pos = min(ear_pos, bar_width)
                cv2.rectangle(frame, (bar_x, bar_y), (bar_x + ear_pos, bar_y + bar_height), (0, 255, 255), -1)
            else:
                cv2.putText(frame, f'EAR: {ear_raw:.4f}', (10, info_y + 25), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            
            if face_detected:
                cv2.putText(frame, eyes_status, (10, info_y + 120), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, status_color, 2)
            
            # Mostrar contador de parpadeos con mejor diseño
            total_blinks = session.total_blinks if session else blink_counter
            
            # Panel de parpadeos con gradiente
            overlay2 = frame.copy()
            cv2.rectangle(overlay2, (10, height - 90), (280, height - 20), (50, 50, 50), -1)
            frame = cv2.addWeighted(overlay2, 0.6, frame, 0.4, 0)
            
            cv2.putText(frame, 'PARPADEOS:', (20, height - 60), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            cv2.putText(frame, f'{total_blinks}', (180, height - 55), 
                       cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 255, 255), 3)
            
            if session:
                cv2.putText(frame, f'Sesion ID: {session.id}', (20, height - 30), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (100, 255, 100), 1)
            
            # Codificar frame como JPEG
            ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            frame_bytes = buffer.tobytes()
            
            # Yield frame en formato multipart
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
            
            time.sleep(0.033)  # ~30 FPS
    
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


@login_required
def session_metrics(request):
    """Return current session metrics as JSON"""
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


# ============================================================================
# CONTROL DE SESIONES
# ============================================================================
@login_required
@require_http_methods(["POST"])
def start_webcam_test(request):
    global webcam_global, streaming_active, current_session_id
    global aux_counter, blink_counter, debounce_counter, last_ear_values
    global CALIBRATION_SAMPLES, EAR_CALIBRATION_MODE
    
    print("=== START_WEBCAM_TEST LLAMADO ===")
    
    # Resetear TODOS los contadores y calibración
    aux_counter = 0
    blink_counter = 0
    debounce_counter = 0
    last_ear_values = []
    CALIBRATION_SAMPLES = []
    EAR_CALIBRATION_MODE = True
    
    with webcam_lock:
        if webcam_global is None:
            webcam_global = cv2.VideoCapture(0)
            if not webcam_global.isOpened():
                webcam_global = None
                return JsonResponse({
                    'status': 'error', 
                    'message': 'No se pudo abrir la webcam'
                })
    
    try:
        session = MonitorSession.objects.create(
            user=request.user,
            start_time=timezone.now(),
            metadata={}
        )
        current_session_id = session.id
        
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
    global webcam_global, streaming_active, current_session_id
    
    print("=== STOP_WEBCAM_TEST LLAMADO ===")
    
    streaming_active = False
    time.sleep(0.2)
    
    if current_session_id:
        try:
            session = MonitorSession.objects.get(
                id=current_session_id,
                user=request.user
            )
            session.end_time = timezone.now()
            session.save()
            
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


@login_required
@csrf_exempt
def start_session(request):
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