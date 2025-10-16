
from django.shortcuts import render

# Create your views here.

from django.views.generic import TemplateView
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from apps.security.components.menu_module import MenuModule
from apps.security.components.group_session import UserGroupSession
from django.db.models import Avg, Count, Q
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.core.cache import cache

# Image processing
import cv2
import numpy as np
import base64
from .models import MonitorSession, BlinkEvent, AlertEvent

# Load Haar cascades for face and eye detection. Provide fallback to packaged cascades.
try:
    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
    eye_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_eye.xml')
except Exception:
    face_cascade = None
    eye_cascade = None

@method_decorator(login_required, name='dispatch')
class ModuloTemplateView(TemplateView):
    template_name = 'monitoring/MHome.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = "VisionPulse - Monitoreo"
        
        # Configurar sesión de grupo si no existe
        user_session = UserGroupSession(self.request)
        user_session.set_group_session()
        
        MenuModule(self.request).fill(context)
        # Extraer los menús si existen
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

        # Add recent sessions
        context['recent_sessions'] = MonitorSession.objects.filter(
            user=self.request.user
        ).order_by('-start_time')[:5]
        
        return context


@method_decorator(login_required, name='dispatch')
class SessionListView(TemplateView):
    template_name = 'monitoring/session_list.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = "VisionPulse - Historial de Sesiones"
        
        # Setup menu
        user_session = UserGroupSession(self.request)
        user_session.set_group_session()
        MenuModule(self.request).fill(context)

        # Get sessions with stats
        sessions = MonitorSession.objects.filter(
            user=self.request.user
        ).order_by('-start_time')

        # Add stats
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

        # Setup menu
        user_session = UserGroupSession(self.request)
        user_session.set_group_session()
        MenuModule(self.request).fill(context)

        # Get timeline of events
        blinks = list(session.blink_events.all())
        alerts = list(session.alerts.all())

        # Merge events chronologically
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


def _decode_base64_image(data_url):
    """Decodifica una imagen enviada como data URL (base64) y la devuelve como array BGR para OpenCV."""
    if not data_url:
        return None
    # data_url can be like: data:image/jpeg;base64,/9j/4AAQ...
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
    """Compute a simple proxy metric for eye openness based on eye bounding box height/width.
    Returns avg_ear (0..1) and blink_detected (bool) using a naive threshold.
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
    # Normalize to approx 0..1 by clamping typical eye ratio range (0.1..0.35)
    norm = (avg - 0.08) / (0.4 - 0.08)
    avg_ear = max(0.0, min(1.0, norm))
    # Blink if avg_ear falls below a threshold
    blink = avg_ear < 0.15
    return avg_ear, blink


@login_required
@csrf_exempt
def start_session(request):
    """Start a new MonitorSession for the logged-in user. Returns session id."""
    if request.method != 'POST':
        return HttpResponseBadRequest('POST required')
    session = MonitorSession.objects.create(user=request.user, start_time=timezone.now(), metadata={})
    # Initialize cache state for blink detection
    cache.set(f'monitor:{session.id}:last_blink', False, timeout=3600)
    cache.set(f'monitor:{session.id}:blink_count', 0, timeout=3600)
    return JsonResponse({'session_id': session.id})


@login_required
@csrf_exempt
def upload_frame(request):
    """Endpoint to receive a base64 frame, analyze it with OpenCV and update metrics.
    Expects JSON: {session_id, image: data_url}
    """
    if request.method != 'POST':
        return HttpResponseBadRequest('POST required')
    try:
        data = request.POST or request.body
        # request.POST may not parse JSON; try parsing JSON body
        import json
        if hasattr(request, 'body') and request.content_type == 'application/json':
            payload = json.loads(request.body.decode('utf-8'))
            session_id = payload.get('session_id')
            image_data = payload.get('image')
        else:
            session_id = request.POST.get('session_id')
            image_data = request.POST.get('image')
    except Exception:
        return HttpResponseBadRequest('invalid payload')

    if not session_id or not image_data:
        return HttpResponseBadRequest('session_id and image required')

    try:
        session = MonitorSession.objects.get(id=session_id, user=request.user)
    except MonitorSession.DoesNotExist:
        return HttpResponseBadRequest('invalid session')

    img = _decode_base64_image(image_data)
    if img is None:
        return HttpResponseBadRequest('invalid image')

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    faces = []
    eyes = []
    if face_cascade is not None:
        faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60))
        # For each face, search eyes inside region
        for (x, y, w, h) in faces:
            roi_gray = gray[y:y + h, x:x + w]
            detected_eyes = eye_cascade.detectMultiScale(roi_gray) if eye_cascade is not None else []
            # Convert eye coords to full image coords
            for (ex, ey, ew, eh) in detected_eyes:
                eyes.append((x + ex, y + ey, ew, eh))
    else:
        # Fallback: try eye cascade on whole image
        if eye_cascade is not None:
            eyes = eye_cascade.detectMultiScale(gray)

    avg_ear, blink = _estimate_eye_metrics(gray, eyes)

    # Update session aggregate
    # naive rolling update: update avg_ear and total_blinks if a blink detected
    if session.avg_ear is None:
        session.avg_ear = avg_ear
    else:
        session.avg_ear = (session.avg_ear + avg_ear) / 2.0

    if blink:
        last_blink = cache.get(f'monitor:{session.id}:last_blink', False)
        if not last_blink:
            # new blink
            bc = cache.get(f'monitor:{session.id}:blink_count', 0) + 1
            cache.set(f'monitor:{session.id}:blink_count', bc, timeout=3600)
            session.total_blinks = (session.total_blinks or 0) + 1
            BlinkEvent.objects.create(session=session, timestamp=timezone.now())
            cache.set(f'monitor:{session.id}:last_blink', True, timeout=2)
        # else: still in blink
    else:
        cache.set(f'monitor:{session.id}:last_blink', False, timeout=3600)

    # Simple alert rule: too many blinks in short time -> fatigue alert
    try:
        bc = cache.get(f'monitor:{session.id}:blink_count', 0)
        if bc and bc > 30:
            session.alerts_count = (session.alerts_count or 0) + 1
            AlertEvent.objects.create(session=session, alert_type=AlertEvent.ALERT_FATIGUE,
                                      triggered_at=timezone.now(), metadata={'blink_count': bc})
            # reset blink_count after generating alert
            cache.set(f'monitor:{session.id}:blink_count', 0, timeout=3600)
    except Exception:
        pass

    # Update timestamps
    session.save()

    return JsonResponse({
        'ok': True,
        'avg_ear': session.avg_ear,
        'total_blinks': session.total_blinks,
        'face_detected': len(faces) > 0,
        'eyes_detected': len(eyes) > 0
    })


@login_required
@csrf_exempt
def stop_session(request):
    """Stop the session and compute duration."""
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
    # cleanup cache
    cache.delete(f'monitor:{session.id}:last_blink')
    cache.delete(f'monitor:{session.id}:blink_count')
    return JsonResponse({'ok': True, 'duration_seconds': session.duration_seconds})



'''' Ejemplo de implementación de un sistema de monitoreo de parpadeo ocular usando OpenCV y Django.   
import cv2
import numpy as np
import json
import threading
import time
from django.http import StreamingHttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from datetime import datetime
from pathlib import Path

# Variables globales para almacenar datos
blink_data = {
    'blink_count': 0,
    'last_blink': None,
    'blink_history': [],
    'eye_closure_duration': 0,
    'face_detected': False,
    'eyes_detected': 0,
    'status': 'Buscando rostro...'
}

class EyeTracker:
    def __init__(self):
        self.video = cv2.VideoCapture(0)
        self.video.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.video.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        
        self.blink_count = 0
        self.eye_closure_start = None
        self.consecutive_frames = 0
        self.blink_cooldown = 0
        
        # Cargar clasificadores Haar
        self.face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        self.eye_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_eye.xml')
        
        (self.grabbed, self.frame) = self.video.read()
        self.running = True
        threading.Thread(target=self.update, args=()).start()

    def __del__(self):
        self.running = False
        self.video.release()

    def detect_eyes(self, face_roi_gray, face_roi_color):
        """Detecta ojos en la región de la cara con parámetros optimizados"""
        # Reducir la región de búsqueda a la parte superior de la cara (donde están los ojos)
        height, width = face_roi_gray.shape
        eye_region = face_roi_gray[0:int(height*0.6), 0:width]
        
        # Detectar ojos con parámetros optimizados
        eyes = self.eye_cascade.detectMultiScale(
            eye_region,
            scaleFactor=1.1,
            minNeighbors=5,
            minSize=(20, 20),
            flags=cv2.CASCADE_SCALE_IMAGE
        )
        
        # Ajustar coordenadas de los ojos a la región completa
        adjusted_eyes = []
        for (ex, ey, ew, eh) in eyes:
            adjusted_eyes.append((ex, ey, ew, eh))
        
        return adjusted_eyes

    def get_frame(self):
        image = self.frame.copy()
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        
        # Detectar caras
        faces = self.face_cascade.detectMultiScale(
            gray,
            scaleFactor=1.1,
            minNeighbors=5,
            minSize=(30, 30),
            flags=cv2.CASCADE_SCALE_IMAGE
        )
        
        current_blink = False
        eyes_detected = 0
        
        # Cooldown para evitar detecciones múltiples del mismo parpadeo
        if self.blink_cooldown > 0:
            self.blink_cooldown -= 1
        
        for (x, y, w, h) in faces:
            # Dibujar rectángulo alrededor del rostro
            cv2.rectangle(image, (x, y), (x + w, y + h), (0, 255, 0), 2)
            cv2.putText(image, "Rostro", (x, y-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
            
            # Región de interés (cara)
            roi_gray = gray[y:y+h, x:x+w]
            roi_color = image[y:y+h, x:x+w]
            
            # Detectar ojos en la cara
            eyes = self.detect_eyes(roi_gray, roi_color)
            eyes_detected = len(eyes)
            
            # Dibujar rectángulos alrededor de los ojos
            for (ex, ey, ew, eh) in eyes:
                cv2.rectangle(roi_color, (ex, ey), (ex + ew, ey + eh), (255, 0, 0), 2)
                cv2.putText(roi_color, "Ojo", (ex, ey-5), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 0, 0), 1)
            
            # Lógica de detección de parpadeos
            if eyes_detected >= 2:  # Ambos ojos detectados (abiertos)
                if self.consecutive_frames >= 3 and self.blink_cooldown == 0:  # Parpadeo válido
                    self.blink_count += 1
                    current_blink = True
                    blink_duration = time.time() - self.eye_closure_start if self.eye_closure_start else 0.3
                    
                    # Actualizar datos globales
                    blink_data['blink_count'] = self.blink_count
                    blink_data['last_blink'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    blink_data['blink_history'].append({
                        'timestamp': blink_data['last_blink'],
                        'duration': round(blink_duration, 2),
                        'eyes_detected': eyes_detected
                    })
                    blink_data['eye_closure_duration'] = blink_duration
                    
                    # Activar cooldown
                    self.blink_cooldown = 10  # ~0.3 segundos a 30 FPS
                
                self.consecutive_frames = 0
                self.eye_closure_start = None
                blink_data['status'] = 'Ojos abiertos'
                
            elif eyes_detected < 2 and eyes_detected > 0:  # Parpadeo parcial
                self.consecutive_frames += 1
                if self.eye_closure_start is None:
                    self.eye_closure_start = time.time()
                blink_data['status'] = 'Parpadeando...'
            elif eyes_detected == 0:  # Posible parpadeo completo
                self.consecutive_frames += 1
                if self.eye_closure_start is None:
                    self.eye_closure_start = time.time()
                blink_data['status'] = 'Ojos cerrados'
        
        # Actualizar datos globales
        blink_data['face_detected'] = len(faces) > 0
        blink_data['eyes_detected'] = eyes_detected
        
        # Mostrar información en pantalla
        status_color = (0, 255, 0) if blink_data['status'] == 'Ojos abiertos' else (0, 0, 255)
        
        cv2.putText(image, f"Parpadeos: {self.blink_count}", (10, 30), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        cv2.putText(image, f"Ojos detectados: {eyes_detected}", (10, 60), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        cv2.putText(image, f"Estado: {blink_data['status']}", (10, 90), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, status_color, 2)
        cv2.putText(image, f"Caras: {len(faces)}", (10, 120), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        
        # Mostrar instrucciones
        cv2.putText(image, "Asegurate de tener buena iluminacion", (10, 400), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        cv2.putText(image, "Mantente frente a la camara", (10, 420), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        
        _, jpeg = cv2.imencode('.jpg', image)
        return jpeg.tobytes(), current_blink

    def update(self):
        while self.running:
            (self.grabbed, self.frame) = self.video.read()
            time.sleep(0.03)  # Controlar FPS

# Instancia global del tracker
eye_tracker = EyeTracker()

def gen(camera):
    while True:
        frame, blink_detected = camera.get_frame()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n\r\n')

def camera_view(request):
    return render(request, 'eye_tracker.html')

def video_feed(request):
    return StreamingHttpResponse(gen(eye_tracker),
                    content_type='multipart/x-mixed-replace; boundary=frame')

@csrf_exempt
def save_data(request):
    if request.method == 'POST':
        try:
            # Crear directorio de datos si no existe
            data_dir = Path("blink_data")
            data_dir.mkdir(exist_ok=True)
            
            # Guardar datos en archivo JSON
            filename = data_dir / f"blink_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            
            with open(filename, 'w') as f:
                json.dump(blink_data, f, indent=4, default=str)
            
            return JsonResponse({
                'status': 'success', 
                'message': f'Datos guardados correctamente en {filename}',
                'file': str(filename)
            })
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)})
    
    return JsonResponse({'status': 'error', 'message': 'Método no permitido'})

def get_blink_data(request):
    return JsonResponse(blink_data)

@csrf_exempt
def reset_counter(request):
    if request.method == 'POST':
        eye_tracker.blink_count = 0
        blink_data['blink_count'] = 0
        blink_data['blink_history'] = []
        blink_data['last_blink'] = None
        return JsonResponse({'status': 'success', 'message': 'Contador reiniciado'})

@csrf_exempt
def export_data(request):
    if request.method == 'POST':
        try:
            data_dir = Path("blink_data")
            data_dir.mkdir(exist_ok=True)
            
            filename = data_dir / f"export_blink_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            
            export_data = {
                'export_timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'summary': {
                    'total_blinks': blink_data['blink_count'],
                    'session_duration': 'N/A',
                    'average_blink_rate': 'N/A'
                },
                'detailed_data': blink_data
            }
            
            with open(filename, 'w') as f:
                json.dump(export_data, f, indent=4, default=str)
            
            return JsonResponse({
                'status': 'success', 
                'message': f'Exportación completada: {filename}',
                'file': str(filename)
            })
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}) 
        
'''