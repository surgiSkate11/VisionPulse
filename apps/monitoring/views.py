# --- Imports ---
from django.shortcuts import get_object_or_404
from django.views.generic import TemplateView, ListView, DetailView
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils.decorators import method_decorator
from django.http import JsonResponse, HttpResponseBadRequest, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from .models import MonitorSession, BlinkEvent, AlertEvent, SessionPause
from apps.security.components.sidebar_menu_mixin import SidebarMenuMixin
import cv2
import mediapipe as mp
import threading
import time
import numpy as np
from math import hypot
from dataclasses import dataclass
from typing import Optional, Dict, Any, Tuple, List
from datetime import timedelta
import json
import os
import logging

# Configuración de logging
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'  # Reduce TF logging
logging.getLogger('mediapipe').setLevel(logging.ERROR)  # Reduce MediaPipe logging

mp_face_mesh = mp.solutions.face_mesh

@dataclass
class EyePoints:
    """Puntos de referencia para los ojos"""
    LEFT_EYE = [33, 160, 158, 133, 153, 144]
    RIGHT_EYE = [362, 385, 387, 263, 373, 380]

class BlinkDetector:
    """Clase para la detección de parpadeos"""
    
    def __init__(self):
        self.VERTICAL_DISTANCE_THRESHOLD = 5
        self.EAR_THRESHOLD = 0.20
        self.MIN_BLINK_DURATION = 0.01
        self.MAX_BLINK_DURATION = 0.35
        self.DEBOUNCE_TIME = 0.15
        
        print("[INIT] Inicializando detector de parpadeos...")
        self.face_mesh = mp_face_mesh.FaceMesh(
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )
        
        self.last_blink_time = 0
        self.eye_closed_time = 0
        self.is_eye_closed = False
        print("[INIT] Detector inicializado correctamente")
        
    def calculate_ear(self, eye_points: list) -> float:
        """Calcula el EAR (Eye Aspect Ratio)"""
        try:
            height = abs(eye_points[1][1] - eye_points[5][1])
            width = hypot(eye_points[0][0] - eye_points[3][0],
                         eye_points[0][1] - eye_points[3][1])
            
            ear = height / width if width > 0 else 0
            return ear
        except (IndexError, ZeroDivisionError) as e:
            print(f"[ERROR] Error calculando EAR: {str(e)}")
            return 0.0
        except Exception as e:
            print(f"[ERROR] Error inesperado calculando EAR: {str(e)}")
            return 0.0
    
    def detect_blink(self, frame) -> Tuple[bool, Dict[str, Any]]:
        """Detecta parpadeos y retorna métricas"""
        try:
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = self.face_mesh.process(rgb_frame)
        except Exception as e:
            print(f"[ERROR] Error procesando frame: {str(e)}")
            return False, {
                'avg_ear': 0.0,
                'focus': 'Error',
                'faces': 0,
                'eyes_detected': False
            }
        
        metrics = {
            'avg_ear': 0.0,
            'focus': 'No detectado',
            'faces': 0,
            'eyes_detected': False
        }
        
        if results.multi_face_landmarks:
            metrics['faces'] = len(results.multi_face_landmarks)
            try:
                face_landmarks = results.multi_face_landmarks[0]
                
                # Obtener puntos de los ojos
                left_eye = [[int(face_landmarks.landmark[point].x * frame.shape[1]),
                            int(face_landmarks.landmark[point].y * frame.shape[0])]
                           for point in EyePoints.LEFT_EYE]
                
                right_eye = [[int(face_landmarks.landmark[point].x * frame.shape[1]),
                             int(face_landmarks.landmark[point].y * frame.shape[0])]
                            for point in EyePoints.RIGHT_EYE]
                
                # Calcular EAR promedio
                left_ear = self.calculate_ear(left_eye)
                right_ear = self.calculate_ear(right_eye)
                avg_ear = (left_ear + right_ear) / 2
                metrics['avg_ear'] = avg_ear
                metrics['eyes_detected'] = True
                
                # Detectar parpadeo
                current_time = time.time()
                is_blink = False
                
                if avg_ear < self.EAR_THRESHOLD:
                    if not self.is_eye_closed:
                        self.eye_closed_time = current_time
                        self.is_eye_closed = True
                else:
                    if self.is_eye_closed:
                        blink_duration = current_time - self.eye_closed_time
                        if (self.MIN_BLINK_DURATION <= blink_duration <= self.MAX_BLINK_DURATION and
                            current_time - self.last_blink_time > self.DEBOUNCE_TIME):
                            self.last_blink_time = current_time
                            is_blink = True
                    self.is_eye_closed = False
                
                metrics['focus'] = 'Atento' if avg_ear > self.EAR_THRESHOLD else 'Distraído'
                return is_blink, metrics
                
            except Exception as e:
                print(f"[ERROR] Error procesando landmarks: {str(e)}")
                return False, metrics
            
        return False, metrics

class CameraManager:
    """Clase para gestionar la cámara y el procesamiento de video"""
    
    def __init__(self):
        self._internal_lock = threading.Lock()
        self._metrics_lock = threading.Lock()
        self.video = None
        self.is_running = False
        self.is_paused = False
        self.session_id = None
        self.pause_frame = None
        self.pause_metrics = None
        self.latest_metrics = {}
        self.blink_detector = BlinkDetector()
        self.blink_counter = 0
        self.last_frame_time = 0
        self.frame_interval = 1.0 / 30
        self.error_count = 0
        self.max_errors = 3
        
    def start_camera(self) -> bool:
        """Inicia la cámara con reintentos y configuración optimizada (no bloqueante)"""
        # No usar locks de inicialización para evitar bloqueos
        if self.is_running:
            logging.warning("[CAMERA] Intento de iniciar cámara ya activa")
            return True

        try:
            max_retries = 2  # más rápido
            retry_count = 0

            # Limpiar cualquier instancia previa
            self.stop_camera()

            while retry_count < max_retries:
                try:
                    logging.info(f"[CAMERA] Intento {retry_count + 1} de iniciar cámara...")

                    # Windows: usar CAP_DSHOW para abrir más rápido
                    self.video = cv2.VideoCapture(0, cv2.CAP_DSHOW)

                    if not self.video.isOpened():
                        logging.warning("[CAMERA] Índice 0 falló, probando índice 1...")
                        try:
                            self.video.release()
                        except Exception:
                            pass
                        self.video = cv2.VideoCapture(1, cv2.CAP_DSHOW)

                    if not self.video.isOpened():
                        raise Exception("No se encontró ninguna cámara disponible")

                    logging.info("[CAMERA] Cámara abierta exitosamente")

                    # Configuración mínima para iniciar rápido
                    self.video.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                    self.video.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                    self.video.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

                    # Leer un frame para validar
                    ret, frame = self.video.read()
                    if not ret or frame is None:
                        raise Exception("No se pudieron leer frames de la cámara")

                    # Marcar como running antes de retornar
                    self.is_running = True
                    self.error_count = 0
                    self.last_frame_time = time.time()
                    logging.info("[CAMERA] Cámara iniciada y probada correctamente")
                    return True

                except Exception as e:
                    retry_count += 1
                    logging.error(f"[CAMERA] Intento {retry_count} falló: {str(e)}")
                    if self.video:
                        try:
                            self.video.release()
                        except Exception:
                            pass
                        self.video = None

                    if retry_count < max_retries:
                        time.sleep(0.5)

            # Si llegamos aquí, fallaron todos los intentos
            self.is_running = False
            self.video = None
            error_msg = f"No se pudo iniciar la cámara después de {max_retries} intentos"
            logging.error(f"[CAMERA] {error_msg}")
            return False

        except Exception as e:
            logging.exception(f"[CAMERA] Error inesperado en start_camera: {e}")
            self.is_running = False
            self.video = None
            return False
    
    def stop_camera(self):
        """Detiene la cámara de forma segura"""
        try:
            was_running = self.is_running
            self.is_running = False  # Marcar como no running PRIMERO

            if self.video:
                try:
                    if self.video.isOpened():
                        self.video.release()
                except Exception as e:
                    logging.error(f"[CAMERA] Error al liberar cámara: {e}")
                finally:
                    self.video = None

            self.session_id = None
            self.blink_counter = 0
            self.is_paused = False
            self.pause_frame = None
            self.pause_metrics = None

            if was_running:
                logging.info("[CAMERA] Cámara detenida correctamente")

        except Exception as e:
            logging.error(f"[CAMERA] Error en stop_camera: {e}")
    
    def get_frame(self) -> Tuple[Optional[np.ndarray], Dict[str, Any]]:
        """Obtiene un frame de la cámara y procesa métricas"""
        # NUEVO: No usar lock aquí para evitar bloqueos durante inicialización
        current_time = time.time()
        
        # Verificar estado básico sin lock
        if not self.is_running:
            return None, {'error': 'camera_not_running', 'is_running': False}
        
        if not self.video or not self.video.isOpened():
            logging.warning("[CAMERA] Video object es None o no está abierto")
            return None, {'error': 'camera_not_initialized', 'is_running': self.is_running}
        
        # Retornar frame pausado si está en pausa
        if self.is_paused:
            return self.pause_frame, self.pause_metrics or {'status': 'paused'}

        # Control de FPS
        time_since_last_frame = current_time - self.last_frame_time
        if time_since_last_frame < self.frame_interval:
            time.sleep(self.frame_interval - time_since_last_frame)

        try:
            ret, frame = self.video.read()
            if not ret or frame is None:
                self.error_count += 1
                if self.error_count >= self.max_errors:
                    self.handle_camera_error()
                logging.warning(f"[CAMERA] Error al leer frame ({self.error_count}/{self.max_errors})")
                return None, {'error': 'frame_read_error'}

            # Procesar frame y detectar parpadeo
            is_blink, metrics = self.blink_detector.detect_blink(frame)

            # Actualizar métricas con thread safety
            with self._metrics_lock:
                self.latest_metrics = {
                    **metrics,
                    'fps': 1.0 / (current_time - self.last_frame_time) if self.last_frame_time > 0 else 0,
                    'error_count': self.error_count
                }

                if is_blink:
                    self.blink_counter += 1
                    self.register_blink()

            self.last_frame_time = current_time
            self.error_count = 0  # Resetear contador de errores en caso de éxito

            return frame, self.latest_metrics

        except Exception as e:
            logging.error(f"[CAMERA] Error procesando frame: {str(e)}")
            self.error_count += 1
            if self.error_count >= self.max_errors:
                self.handle_camera_error()
            return None, {'error': f'processing_error: {str(e)}'}
    
    def handle_camera_error(self):
        """Maneja errores críticos de la cámara intentando reiniciarla"""
        logging.error("[CAMERA] Error crítico detectado, intentando reiniciar la cámara")
        try:
            if self.video and self.video.isOpened():
                self.video.release()
            self.video = None
            time.sleep(2)  # Esperar antes de reiniciar
            
            if self.start_camera():
                logging.info("[CAMERA] Cámara reiniciada exitosamente")
                self.error_count = 0
            else:
                logging.error("[CAMERA] No se pudo reiniciar la cámara")
                self.is_running = False
                
        except Exception as e:
            logging.error(f"[CAMERA] Error durante el reinicio de la cámara: {str(e)}")
            self.is_running = False
    
    def get_latest_metrics(self) -> Dict[str, Any]:
        """Retorna las últimas métricas procesadas con información adicional del sistema"""
        with self._metrics_lock:
            try:
                metrics = self.latest_metrics.copy()
                current_time = time.time()
                
                # Agregar métricas adicionales
                metrics.update({
                    'total_blinks': self.blink_counter,
                    'camera_status': 'running' if self.is_running else 'stopped',
                    'is_paused': self.is_paused,
                    'error_count': self.error_count,
                    'fps': 1.0 / (current_time - self.last_frame_time) if self.last_frame_time > 0 else 0,
                    'system_time': current_time,
                    'uptime': current_time - self.last_frame_time if self.last_frame_time > 0 else 0
                })
                
                if self.session_id:
                    metrics['session_id'] = self.session_id
                    
                return metrics
                
            except Exception as e:
                logging.error(f"[METRICS] Error al obtener métricas: {str(e)}")
                return {
                    'error': str(e),
                    'total_blinks': self.blink_counter,
                    'camera_status': 'error',
                    'is_paused': self.is_paused
                }
    
    def register_blink(self):
        """Registra un parpadeo en la base de datos"""
        if not self.session_id:
            return
            
        try:
            session = MonitorSession.objects.get(id=self.session_id)
            BlinkEvent.objects.create(
                session=session,
                timestamp=timezone.now()
            )
            session.total_blinks = self.blink_counter
            session.save(update_fields=['total_blinks'])
        except MonitorSession.DoesNotExist:
            print(f"[ERROR] Sesión {self.session_id} no encontrada")
        except Exception as e:
            print(f"[ERROR] Error al registrar parpadeo: {str(e)}")

class MonitoringController:
    """Clase para manejar la lógica de negocio y las sesiones de monitoreo"""

    def __init__(self):
        self.camera_manager = CameraManager()
        self.lock = threading.Lock()
        self.session_lock = threading.Lock()
        self.metrics_cache = {}
        self.metrics_cache_time = 0
        self.metrics_cache_duration = 0.5  # 500ms de cache
        self.active_alerts = []
        self.last_alert_time = 0
        self.alert_cooldown = 5.0  # 5 segundos entre alertas
        self.session_data = {
            'id': None,
            'start_time': None,
            'total_duration': 0,
            'effective_duration': 0,
            'pause_duration': 0,
            'alert_count': 0
        }
    
    def start_session(self, user) -> Tuple[bool, Optional[str], Optional[MonitorSession]]:
        """Inicia una nueva sesión de monitoreo"""
        with self.session_lock:
            if self.camera_manager.is_running:
                logging.warning(f"[SESSION] Sesión ya activa. Usuario: {user.username}")
                return False, "Ya hay una sesión activa", None

            try:
                # Verificar sesiones sin cerrar del usuario
                unclosed_sessions = MonitorSession.objects.filter(
                    user=user,
                    end_time__isnull=True
                ).exists()

                if unclosed_sessions:
                    logging.warning(f"[SESSION] Usuario {user.username} tiene sesiones sin cerrar")
                    # Cerrar sesiones antiguas
                    MonitorSession.objects.filter(
                        user=user,
                        end_time__isnull=True
                    ).update(
                        end_time=timezone.now(),
                        status='interrupted'
                    )

                # Iniciar cámara sin timeout externo; confiar en los reintentos internos
                logging.info("[SESSION] Iniciando cámara...")
                if not self.camera_manager.start_camera():
                    error_msg = "No se pudo iniciar la cámara. Verifica que esté conectada y no esté en uso."
                    logging.error(f"[SESSION] {error_msg}")
                    return False, error_msg, None

                logging.info("[SESSION] Cámara iniciada exitosamente")

                # Crear nueva sesión
                start_time = timezone.now()
                session = MonitorSession.objects.create(
                    user=user,
                    start_time=start_time,
                    status='active',
                    total_blinks=0,
                    total_alerts=0
                )

                # Actualizar estado interno
                self.camera_manager.session_id = session.id
                self.session_data.update({
                    'id': session.id,
                    'start_time': start_time,
                    'total_duration': 0,
                    'effective_duration': 0,
                    'pause_duration': 0,
                    'alert_count': 0
                })

                logging.info(f"[SESSION] Nueva sesión iniciada. ID: {session.id}, Usuario: {user.username}")
                return True, None, session

            except Exception as e:
                error_msg = f"Error al crear sesión: {str(e)}"
                logging.error(f"[SESSION] {error_msg}")
                logging.exception(e)

                # Limpieza en caso de error
                self.camera_manager.stop_camera()
                self.reset_session_data()

                return False, error_msg, None
    
    def reset_session_data(self):
        """Resetea los datos de la sesión actual"""
        self.session_data = {
            'id': None,
            'start_time': None,
            'total_duration': 0,
            'effective_duration': 0,
            'pause_duration': 0,
            'alert_count': 0
        }
        self.active_alerts.clear()
        self.last_alert_time = 0
        self.metrics_cache.clear()
        self.metrics_cache_time = 0
    
    def end_session(self) -> Tuple[bool, Optional[str], Dict[str, Any]]:
        """Finaliza la sesión actual y genera resumen de la sesión"""
        with self.session_lock:
            if not self.camera_manager.is_running:
                logging.warning("[SESSION] Intento de finalizar sesión inactiva")
                return False, "No hay sesión activa", {}
            
            try:
                session_summary = {}
                
                if self.camera_manager.session_id:
                    # Obtener datos finales de la sesión
                    end_time = timezone.now()
                    final_metrics = self.camera_manager.get_latest_metrics()
                    
                    try:
                        session = MonitorSession.objects.get(
                            id=self.camera_manager.session_id
                        )
                        
                        # Calcular duraciones
                        total_duration = (end_time - session.start_time).total_seconds()
                        pause_duration = sum(
                            (p.resume_time - p.pause_time).total_seconds()
                            for p in session.pauses.all()
                            if p.resume_time
                        )
                        effective_duration = total_duration - pause_duration
                        
                        # Actualizar sesión con datos finales
                        session.end_time = end_time
                        session.total_blinks = self.camera_manager.blink_counter
                        session.total_duration = total_duration
                        session.effective_duration = effective_duration
                        session.pause_duration = pause_duration
                        session.total_alerts = self.session_data['alert_count']
                        session.status = 'completed'
                        session.final_metrics = json.dumps(final_metrics)
                        session.save()
                        
                        # Preparar resumen de la sesión
                        session_summary = {
                            'session_id': session.id,
                            'start_time': session.start_time.isoformat(),
                            'end_time': end_time.isoformat(),
                            'total_duration': total_duration,
                            'effective_duration': effective_duration,
                            'pause_duration': pause_duration,
                            'total_blinks': self.camera_manager.blink_counter,
                            'total_alerts': self.session_data['alert_count'],
                            'avg_blink_rate': (self.camera_manager.blink_counter / effective_duration) if effective_duration > 0 else 0,
                            'final_metrics': final_metrics
                        }
                        
                        logging.info(f"[SESSION] Sesión {session.id} finalizada correctamente")
                        
                    except MonitorSession.DoesNotExist:
                        logging.error(f"[SESSION] Sesión {self.camera_manager.session_id} no encontrada")
                        return False, "Sesión no encontrada", {}
                
                # Limpiar estado
                self.camera_manager.stop_camera()
                self.reset_session_data()
                
                return True, "Sesión finalizada correctamente", session_summary
                
            except Exception as e:
                error_msg = f"Error al finalizar sesión: {str(e)}"
                logging.error(f"[SESSION] {error_msg}")
                
                # Intentar limpieza de emergencia
                try:
                    self.camera_manager.stop_camera()
                    self.reset_session_data()
                except Exception as cleanup_error:
                    logging.error(f"[SESSION] Error en limpieza de emergencia: {str(cleanup_error)}")
                
                return False, error_msg, {}
    
    def pause_session(self) -> Tuple[bool, str, Dict[str, Any]]:
        """Pausa la sesión actual"""
        with self.lock:
            if not self.camera_manager.is_running:
                return False, "No hay sesión activa", {}
                
            try:
                if not self.camera_manager.session_id:
                    return False, "No hay ID de sesión", {}
                    
                session = MonitorSession.objects.get(
                    id=self.camera_manager.session_id
                )
                
                existing_pause = session.pauses.filter(
                    resume_time__isnull=True
                ).first()
                
                if existing_pause:
                    return True, "La sesión ya está pausada", {
                        'is_paused': True,
                        'session_id': self.camera_manager.session_id,
                        'blink_count': self.camera_manager.blink_counter
                    }
                
                pause = SessionPause.objects.create(
                    session=session,
                    pause_time=timezone.now()
                )
                
                with self.camera_manager._internal_lock:
                    self.camera_manager.is_paused = True
                    frame, metrics = self.camera_manager.get_frame()
                    self.camera_manager.pause_frame = frame
                    self.camera_manager.pause_metrics = metrics
                    current_blinks = self.camera_manager.blink_counter
                    session.total_blinks = current_blinks
                    session.save(update_fields=['total_blinks'])
                
                print(f"[PAUSE] Sesión {session.id} pausada. Parpadeos: {current_blinks}")
                
                return True, "Sesión pausada correctamente", {
                    'is_paused': True,
                    'session_id': self.camera_manager.session_id,
                    'blink_count': current_blinks,
                    'timestamp': timezone.now().isoformat()
                }
                
            except MonitorSession.DoesNotExist:
                return False, "Sesión no encontrada", {}
            except Exception as e:
                return False, f"Error al pausar: {str(e)}", {}
    
    def resume_session(self) -> Tuple[bool, str, Dict[str, Any]]:
        """Reanuda la sesión actual"""
        with self.lock:
            if not self.camera_manager.is_running:
                return False, "No hay sesión activa", {}
                
            try:
                if not self.camera_manager.session_id:
                    return False, "No hay ID de sesión", {}
                    
                session = MonitorSession.objects.get(
                    id=self.camera_manager.session_id
                )
                
                current_pause = session.pauses.filter(
                    resume_time__isnull=True
                ).last()
                
                if not current_pause:
                    with self.camera_manager._internal_lock:
                        if self.camera_manager.is_paused:
                            self.camera_manager.is_paused = False
                            
                    return True, "La sesión ya está activa", {
                        'is_paused': False,
                        'session_id': self.camera_manager.session_id,
                        'blink_count': self.camera_manager.blink_counter
                    }
                
                resume_time = timezone.now()
                
                with self.camera_manager._internal_lock:
                    try:
                        # Reinicializar la captura de video
                        if self.camera_manager.video and self.camera_manager.video.isOpened():
                            self.camera_manager.video.release()
                        
                        self.camera_manager.video = cv2.VideoCapture(0)
                        self.camera_manager.video.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                        self.camera_manager.video.set(cv2.CAP_PROP_FPS, 30)
                        
                        if not self.camera_manager.video.isOpened():
                            raise Exception("No se pudo reiniciar la cámara")
                        
                        # Limpiar frames de pausa
                        self.camera_manager.pause_frame = None
                        self.camera_manager.pause_metrics = None
                        self.camera_manager.is_paused = False
                        
                        # Actualizar el registro de pausa
                        current_pause.resume_time = resume_time
                        current_pause.save()
                        
                        current_blinks = self.camera_manager.blink_counter
                        print(f"[RESUME] Sesión {session.id} reanudada. Parpadeos: {current_blinks}")
                        
                    except Exception as cam_error:
                        print(f"[ERROR] Error al reiniciar cámara: {str(cam_error)}")
                        raise Exception(f"Error al reiniciar cámara: {str(cam_error)}")
                
                return True, "Sesión reanudada correctamente", {
                    'is_paused': False,
                    'session_id': self.camera_manager.session_id,
                    'blink_count': self.camera_manager.blink_counter,
                    'timestamp': resume_time.isoformat()
                }
                
            except MonitorSession.DoesNotExist:
                return False, "Sesión no encontrada", {}
            except Exception as e:
                return False, f"Error al reanudar: {str(e)}", {}
    
    def check_alertas(self, metrics: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Verifica y genera alertas basadas en las métricas actuales"""
        current_time = time.time()
        new_alerts = []
        
        # Evitar alertas durante el período de cooldown
        if current_time - self.last_alert_time < self.alert_cooldown:
            return []
        
        try:
            # Verificar diferentes condiciones para alertas
            if metrics.get('avg_ear', 1.0) < 0.15:  # Ojos muy cerrados
                new_alerts.append({
                    'type': 'fatigue',
                    'level': 'high',
                    'message': 'Detectada fatiga visual severa',
                    'timestamp': current_time
                })
            
            if metrics.get('focus', 'No detectado') == 'Distraído':
                new_alerts.append({
                    'type': 'distraction',
                    'level': 'medium',
                    'message': 'Posible distracción detectada',
                    'timestamp': current_time
                })
            
            if metrics.get('faces', 0) == 0:
                new_alerts.append({
                    'type': 'no_face',
                    'level': 'low',
                    'message': 'Rostro no detectado',
                    'timestamp': current_time
                })
            
            # Si hay nuevas alertas, actualizar estado
            if new_alerts:
                self.last_alert_time = current_time
                self.session_data['alert_count'] += len(new_alerts)
                
                # Registrar alertas en la base de datos
                if self.camera_manager.session_id:
                    try:
                        session = MonitorSession.objects.get(id=self.camera_manager.session_id)
                        for alert in new_alerts:
                            AlertEvent.objects.create(
                                session=session,
                                alert_type=alert['type'],
                                level=alert['level'],
                                message=alert['message'],
                                timestamp=timezone.now()
                            )
                    except Exception as e:
                        logging.error(f"[ALERT] Error al registrar alertas: {str(e)}")
            
            return new_alerts
            
        except Exception as e:
            logging.error(f"[ALERT] Error al procesar alertas: {str(e)}")
            return []
    
    def get_metrics(self) -> Dict[str, Any]:
        """Obtiene las métricas actuales con caché y procesamiento de alertas"""
        current_time = time.time()
        
        # Verificar si podemos usar el caché
        if (current_time - self.metrics_cache_time < self.metrics_cache_duration and 
            self.metrics_cache):
            return self.metrics_cache
        
        with self.lock:
            if not self.camera_manager.is_running:
                return {
                    'status': 'inactive',
                    'message': 'No hay sesión activa',
                    'metrics': {
                        'ear': 0.0,
                        'focus': 'Inactivo',
                        'faces': 0,
                        'eyes_detected': False,
                        'face_detected': False,
                        'total_blinks': 0
                    },
                    'is_paused': False,
                    'alerts': []
                }
            
            try:
                # Obtener métricas básicas
                base_metrics = self.camera_manager.get_latest_metrics()
                raw_metrics = {
                    'avg_ear': base_metrics.get('avg_ear', 0.0),
                    'focus': base_metrics.get('focus', 'No detectado'),
                    'faces': base_metrics.get('faces', 0),
                    'eyes_detected': base_metrics.get('eyes_detected', False),
                    'total_blinks': base_metrics.get('total_blinks', 0),  # Consistente
                    'blink_count': base_metrics.get('total_blinks', 0),   # Alias para retrocompatibilidad
                }
                is_paused = self.camera_manager.is_paused
                
                # Verificar estado de la sesión
                if self.camera_manager.session_id:
                    try:
                        session = MonitorSession.objects.get(
                            id=self.camera_manager.session_id
                        )
                        if session.end_time:
                            return {
                                'status': 'ended',
                                'message': 'Sesión finalizada',
                                'metrics': raw_metrics,
                                'is_paused': False,
                                'alerts': []
                            }
                            
                        # Calcular métricas de sesión
                        current_time = timezone.now()
                        session_duration = (current_time - session.start_time).total_seconds()
                        pause_duration = sum(
                            (p.resume_time - p.pause_time).total_seconds()
                            for p in session.pauses.all()
                            if p.resume_time
                        )
                        effective_duration = session_duration - pause_duration
                        
                        # Agregar métricas calculadas
                        raw_metrics.update({
                            'session_duration': session_duration,
                            'effective_duration': effective_duration,
                            'blink_rate': (self.camera_manager.blink_counter / effective_duration) if effective_duration > 0 else 0,
                            'alert_count': self.session_data['alert_count']
                        })
                        
                    except MonitorSession.DoesNotExist:
                        logging.error(f"[METRICS] Sesión {self.camera_manager.session_id} no encontrada")
                        return {
                            'status': 'error',
                            'message': 'Sesión no encontrada',
                            'metrics': raw_metrics,
                            'is_paused': False,
                            'alerts': []
                        }
                
                # Procesar alertas
                new_alerts = self.check_alertas(raw_metrics)
                
                # Construir respuesta
                response = {
                    'status': 'success',
                    'metrics': raw_metrics,
                    'is_paused': is_paused,
                    'alerts': new_alerts,
                    'timestamp': time.time()
                }
                
                if is_paused:
                    response['message'] = 'Monitoreo en pausa'
                elif new_alerts:
                    response['message'] = new_alerts[0]['message']
                else:
                    response['message'] = 'Monitoreo activo'
                
                # Actualizar caché
                self.metrics_cache = response
                self.metrics_cache_time = time.time()
                
                return response
                
            except Exception as e:
                error_msg = f"Error al obtener métricas: {str(e)}"
                logging.error(f"[METRICS] {error_msg}")
                
                return {
                    'status': 'error',
                    'message': error_msg,
                    'metrics': {
                        'ear': 0.0,
                        'focus': 'Error',
                        'faces': 0,
                        'eyes_detected': False,
                        'face_detected': False,
                        'total_blinks': 0,
                        'error': str(e)
                    },
                    'is_paused': False,
                    'alerts': []
                }

# Instancia global del controlador
controller = MonitoringController()

def generate_frames():
    """Generador de frames para el streaming de video"""
    while controller.camera_manager.is_running:
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

# --- Views ---
class LiveMonitoringView(LoginRequiredMixin, SidebarMenuMixin, TemplateView):
    """Vista principal para el monitoreo en vivo."""
    template_name = 'monitoring/live_session.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Monitoreo en Vivo'
        context['active_session'] = False
        
        if controller.camera_manager.is_running:
            context['active_session'] = True
            context['session_id'] = controller.camera_manager.session_id
            context['is_paused'] = controller.camera_manager.is_paused
            
            try:
                if controller.camera_manager.session_id:
                    session = MonitorSession.objects.get(
                        id=controller.camera_manager.session_id
                    )
                    context['total_blinks'] = session.total_blinks
                    context['start_time'] = session.start_time
            except MonitorSession.DoesNotExist:
                pass
                
        return context

class SessionListView(LoginRequiredMixin, SidebarMenuMixin, ListView):
    model = MonitorSession
    template_name = 'monitoring/session_list.html'
    context_object_name = 'sessions'
    
    def get_queryset(self):
        return MonitorSession.objects.filter(user=self.request.user).order_by('-start_time')

class SessionDetailView(LoginRequiredMixin, SidebarMenuMixin, DetailView):
    model = MonitorSession
    template_name = 'monitoring/session_detail.html'
    context_object_name = 'session'
    
    def get_queryset(self):
        return MonitorSession.objects.filter(user=self.request.user)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        session = self.object
        
        # Datos para los gráficos
        blinks = list(session.blinks.all().order_by('timestamp'))
        alerts = list(session.alerts.all().order_by('timestamp'))
        
        # Generar etiquetas de tiempo y datos
        time_labels = []
        blinks_data = []
        focus_data = []
        
        if session.start_time and session.end_time:
            duration = (session.end_time - session.start_time).total_seconds()
            interval = max(1, int(duration / 30))  # 30 puntos máximo en el gráfico
            
            current_time = session.start_time
            while current_time <= session.end_time:
                time_labels.append(current_time.strftime('%H:%M:%S'))
                
                # Contar parpadeos en este intervalo
                blinks_in_interval = sum(
                    1 for blink in blinks 
                    if blink.timestamp <= current_time
                )
                blinks_data.append(blinks_in_interval)
                
                # Estado de atención en este intervalo
                alerts_in_interval = [
                    alert for alert in alerts 
                    if alert.timestamp <= current_time and alert.alert_type == 'distraction'
                ]
                focus_data.append(100 if not alerts_in_interval else 50)
                
                current_time += timedelta(seconds=interval)
        
        context.update({
            'time_labels': time_labels,
            'blinks_data': blinks_data,
            'focus_data': focus_data,
            'events': alerts,
            'total_duration': session.total_duration if session.total_duration else 0,
            'effective_duration': session.effective_duration if session.effective_duration else 0,
            'total_blinks': session.total_blinks if session.total_blinks else 0,
            'total_alerts': session.total_alerts if session.total_alerts else 0,
            'page_title': f'Sesión #{session.id}'
        })
        
        return context

# --- API Endpoints ---
@login_required
@csrf_exempt
@require_http_methods(["POST"])
def start_session(request):
    """Inicia una nueva sesión de monitoreo"""
    try:
        logging.info(f"[START] Usuario {request.user.username} intentando iniciar nueva sesión")
        
        # Verificar si hay una sesión activa
        if controller.camera_manager.is_running:
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