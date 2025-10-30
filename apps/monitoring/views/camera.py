import numpy as np

class CameraManager:
    # ...existing code...
    def validate_frame_dimensions(self, frame: np.ndarray) -> bool:
        """
        Valida que el frame tenga dimensiones válidas antes de procesar.
        """
        if frame is None:
            logging.error("[CAMERA] Frame es None")
            return False
        if not hasattr(frame, 'shape') or len(frame.shape) < 2:
            logging.error(f"[CAMERA] Frame sin shape válido: {getattr(frame, 'shape', None)}")
            return False
        h, w = frame.shape[:2]
        if h < 10 or w < 10:
            logging.error(f"[CAMERA] Dimensiones inválidas: h={h}, w={w}")
            return False
        return True
# apps/monitoring/views/camera.py
"""
Módulo para la gestión de cámara y detección de parpadeos.
Contiene las clases BlinkDetector y CameraManager.
"""

import cv2
import mediapipe as mp
import numpy as np
import threading
import time
import numpy as np
from math import hypot
from dataclasses import dataclass
from typing import Optional, Dict, Any, Tuple
import logging
import os
from django.utils import timezone


from ..models import MonitorSession, AlertEvent
from .improved_detector import UnifiedDetectionSystem

# Configuración de logging
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'  # Reduce TF logging
logging.getLogger('mediapipe').setLevel(logging.ERROR)  # Reduce MediaPipe logging

mp_face_mesh = mp.solutions.face_mesh


@dataclass
class EyePoints:
    """Puntos de referencia para los ojos en MediaPipe Face Mesh"""
    LEFT_EYE = [33, 160, 158, 133, 153, 144]
    RIGHT_EYE = [362, 385, 387, 263, 373, 380]


@dataclass
class MouthPoints:
    """Puntos de referencia para la boca en MediaPipe Face Mesh"""
    UPPER_LIP = [61, 185, 40, 39, 37, 0, 267, 269, 270, 409, 291]
    LOWER_LIP = [146, 91, 181, 84, 17, 314, 405, 321, 375, 291]
    # Puntos para calcular MAR (simplificados)
    VERTICAL_TOP = 13      # Centro labio superior
    VERTICAL_BOTTOM = 14   # Centro labio inferior
    LEFT_CORNER = 61       # Comisura izquierda
    RIGHT_CORNER = 291     # Comisura derecha


@dataclass
class HeadPosePoints:
    """Puntos de referencia para estimar la pose de cabeza"""
    NOSE_TIP = 1
    NOSE_BRIDGE = 168
    CHIN = 152
    LEFT_EYE_CORNER = 33
    RIGHT_EYE_CORNER = 263
    LEFT_EAR = 234
    RIGHT_EAR = 454


class BlinkDetector:
    """
    Clase para la detección de parpadeos usando MediaPipe Face Mesh.
    Calcula el Eye Aspect Ratio (EAR) y detecta parpadeos basándose en umbrales configurables.
    """
    
    def __init__(self, user_config=None):
        # Guardar config para uso en otros métodos (e.g., overlay)
        self.user_config = user_config
        # Controles de rendimiento/precisión en runtime
        self.processing_scale = 1.0  # 1.0 = resolución completa; <1.0 reduce costo
        self.overlay_runtime_enabled = True  # Permite desactivar overlay para ahorrar CPU
        # Valores por defecto (constantes que no cambian)
        self.VERTICAL_DISTANCE_THRESHOLD = 5
        self.MIN_BLINK_DURATION = 0.01
        self.MAX_BLINK_DURATION = 0.35
        self.DEBOUNCE_TIME = 0.15
        
        # Configuración personalizada del usuario
        if user_config:
            # Métricas de Ojos
            self.EAR_THRESHOLD = user_config.ear_threshold
            self.BLINK_WINDOW = user_config.blink_window_frames
            # Microsueño: forzar mínimo razonable
            self.MICROSLEEP_DURATION = max(2.0, user_config.microsleep_duration_seconds)
            
            # Tasa de Parpadeo (ahora dividida en low/high)
            self.LOW_BLINK_RATE_THRESHOLD = user_config.low_blink_rate_threshold
            self.HIGH_BLINK_RATE_THRESHOLD = user_config.high_blink_rate_threshold
            
            # Boca y Bostezos
            # Bostezos: Usar el valor configurado por el usuario (más sensible)
            self.MAR_YAWN_THRESHOLD = user_config.yawn_mar_threshold
            self.MIN_YAWN_DURATION = 1.5
            
            # Pose de Cabeza (Distracción y Postura)
            distraction_angle = user_config.distraction_angle_threshold
            self.HEAD_YAW_THRESHOLD = distraction_angle  # Mirar a los lados
            self.HEAD_PITCH_THRESHOLD = distraction_angle * 0.6  # Mirar arriba/abajo (más estricto)
            self.PHONE_USE_PITCH = 25  # Fijo: ángulo específico para uso de celular
            self.PHONE_USE_YAW = 15  # Fijo: mirar ligeramente hacia un lado
            self.POSTURAL_RIGIDITY_DURATION = user_config.postural_rigidity_duration_seconds
            
            # Ambiente
            self.LOW_LIGHT_THRESHOLD = user_config.low_light_threshold
            
            # Sistema de Detección
            detection_confidence = user_config.face_detection_sensitivity
            tracking_confidence = detection_confidence * 0.9
        else:
            # Valores por defecto si no hay configuración de usuario
            self.EAR_THRESHOLD = 0.20
            self.BLINK_WINDOW = 3
            self.MICROSLEEP_DURATION = 2.0  # Aumentado
            self.LOW_BLINK_RATE_THRESHOLD = 10
            self.HIGH_BLINK_RATE_THRESHOLD = 35
            self.MAR_YAWN_THRESHOLD = 0.60  # Default más sensible
            self.MIN_YAWN_DURATION = 1.5
            self.HEAD_YAW_THRESHOLD = 25
            self.HEAD_PITCH_THRESHOLD = 15
            self.PHONE_USE_PITCH = 25
            self.PHONE_USE_YAW = 15
            self.POSTURAL_RIGIDITY_DURATION = 180
            self.LOW_LIGHT_THRESHOLD = 70
            detection_confidence = 0.5
            tracking_confidence = 0.5
        
        print(f"[INIT] Inicializando Face Mesh (alta precisión)")
        print(f"[INIT] EAR threshold: {self.EAR_THRESHOLD}, sensibilidad base: {detection_confidence}")

        # Forzar modo de alta precisión: landmarks refinados y umbrales altos
        min_det_conf = max(0.8, float(detection_confidence))
        min_track_conf = max(0.8, float(tracking_confidence))

        try:
            self.face_mesh = mp_face_mesh.FaceMesh(
                static_image_mode=False,
                max_num_faces=2,  # Permitir detectar hasta 2 caras para ALERT_MULTIPLE_PEOPLE
                refine_landmarks=True,  # Mejora precisión en ojos, labios e iris
                min_detection_confidence=min_det_conf,
                min_tracking_confidence=min_track_conf
            )
            print(f"[INIT] FaceMesh configurado con alta precisión (det={min_det_conf}, track={min_track_conf})")
        except TypeError:
            # Compatibilidad con versiones antiguas de MediaPipe que no acepten static_image_mode
            self.face_mesh = mp_face_mesh.FaceMesh(
                max_num_faces=2,
                refine_landmarks=True,
                min_detection_confidence=min_det_conf,
                min_tracking_confidence=min_track_conf
            )
            print(f"[INIT] FaceMesh (compat) configurado con alta precisión (det={min_det_conf}, track={min_track_conf})")
        
        self.last_blink_time = 0
        self.eye_closed_time = 0
        self.is_eye_closed = False

        # Estado para detección de bostezos
        self.mouth_open_time = 0
        self.is_mouth_open = False
        self.yawn_counter = 0  # Contador de bostezos detectados
        self.last_yawn_time = 0.0  # Cooldown entre bostezos
        self.yawn_cooldown = 3.0   # segundos
        self.yawn_active = False   # evitar duplicados durante la misma apertura de boca
        
        # Historial de pose para detectar rigidez y agitación
        self.head_pose_history = []
        self.MAX_POSE_HISTORY = 30  # Guardar últimos 30 frames (~1 segundo a 30fps)
        
        print("[INIT] Detector inicializado correctamente")
        
    def calculate_ear(self, eye_points: list) -> float:
        """
        Calcula el EAR (Eye Aspect Ratio) para un ojo.
        EAR = altura / anchura del ojo
        """
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
    
    def calculate_mar(self, mouth_landmarks, frame_shape) -> float:
        """
        Calcula el MAR (Mouth Aspect Ratio) para detectar bostezos.
        MAR = altura_boca / anchura_boca
        """
        try:
            # Obtener coordenadas de los puntos clave
            top = mouth_landmarks[MouthPoints.VERTICAL_TOP]
            bottom = mouth_landmarks[MouthPoints.VERTICAL_BOTTOM]
            left = mouth_landmarks[MouthPoints.LEFT_CORNER]
            right = mouth_landmarks[MouthPoints.RIGHT_CORNER]
            
            # Convertir a coordenadas de píxeles
            top_y = int(top.y * frame_shape[0])
            bottom_y = int(bottom.y * frame_shape[0])
            left_x = int(left.x * frame_shape[1])
            right_x = int(right.x * frame_shape[1])
            
            # Calcular altura y anchura
            height = abs(bottom_y - top_y)
            width = abs(right_x - left_x)
            
            mar = height / width if width > 0 else 0
            # Validaciones básicas para evitar outliers extremos
            if not np.isfinite(mar):
                return 0.0
            return float(max(0.0, min(mar, 2.0)))
        except Exception as e:
            print(f"[ERROR] Error calculando MAR: {str(e)}")
            return 0.0
    
    def estimate_head_pose(self, face_landmarks, frame_shape) -> Tuple[float, float, float]:
        """
        Estima la pose de cabeza (yaw, pitch, roll) usando landmarks de MediaPipe.
        Retorna ángulos en grados.
        
        Returns:
            Tuple[float, float, float]: (yaw, pitch, roll)
            - yaw: rotación izquierda/derecha (negativo=izq, positivo=der)
            - pitch: inclinación arriba/abajo (negativo=abajo, positivo=arriba)  
            - roll: inclinación lateral (generalmente no usamos)
        """
        try:
            # Obtener coordenadas 2D de puntos clave
            nose_tip = face_landmarks[HeadPosePoints.NOSE_TIP]
            nose_bridge = face_landmarks[HeadPosePoints.NOSE_BRIDGE]
            chin = face_landmarks[HeadPosePoints.CHIN]
            left_eye = face_landmarks[HeadPosePoints.LEFT_EYE_CORNER]
            right_eye = face_landmarks[HeadPosePoints.RIGHT_EYE_CORNER]

            # Convertir a coordenadas de píxeles
            h, w = frame_shape[:2]

            nose_tip_2d = (int(nose_tip.x * w), int(nose_tip.y * h))
            chin_2d = (int(chin.x * w), int(chin.y * h))
            left_eye_2d = (int(left_eye.x * w), int(left_eye.y * h))
            right_eye_2d = (int(right_eye.x * w), int(right_eye.y * h))

            # Estimar yaw (izquierda/derecha) basado en la posición relativa de la nariz
            eye_center_x = (left_eye_2d[0] + right_eye_2d[0]) / 2
            face_center_x = w / 2
            nose_offset_x = nose_tip_2d[0] - eye_center_x
            face_width = abs(right_eye_2d[0] - left_eye_2d[0])

            # Normalizar y convertir a grados aproximados (-45 a 45 grados)
            yaw = (nose_offset_x / face_width) * 90 if face_width > 0 else 0
            yaw = max(-45, min(45, yaw))  # Limitar rango

            # Estimar pitch (arriba/abajo) basado en la posición vertical de la nariz vs ojos
            eye_center_y = (left_eye_2d[1] + right_eye_2d[1]) / 2
            nose_offset_y = nose_tip_2d[1] - eye_center_y
            face_height = abs(chin_2d[1] - eye_center_y)

            # Normalizar y convertir a grados aproximados (-30 a 30 grados)
            pitch = -(nose_offset_y / face_height) * 60 if face_height > 0 else 0
            pitch = max(-30, min(30, pitch))  # Limitar rango

            # --- CÁLCULO DE ROLL ---
            # Estimar roll (inclinación) basado en la diferencia de altura de los ojos
            delta_y = right_eye_2d[1] - left_eye_2d[1]
            delta_x = right_eye_2d[0] - left_eye_2d[0]

            if delta_x != 0:
                roll = float(np.degrees(np.arctan(delta_y / delta_x)))
            else:
                roll = 0.0

            # Limitar rango razonable
            roll = max(-45, min(45, roll))

            return float(yaw), float(pitch), float(roll)
        except Exception as e:
            print(f"[ERROR] Error estimando pose de cabeza: {str(e)}")
            return 0.0, 0.0, 0.0
    
    def calculate_brightness(self, frame) -> float:
        """
        Calcula el brillo promedio del frame (luminancia).
        
        Returns:
            float: Brillo promedio (0-255)
        """
        try:
            gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            brightness = np.mean(gray_frame)
            return float(brightness)
        except Exception as e:
            print(f"[ERROR] Error calculando brillo: {str(e)}")
            return 0.0
    
    def analyze_head_pose_stability(self) -> Tuple[float, str]:
        """Analiza la estabilidad de la pose de cabeza - VERSIÓN MEJORADA"""
        if len(self.head_pose_history) < 15:  # Aumentado de 10
            return 0.0, 'insufficient_data'

        try:
            yaws = [pose[0] for pose in self.head_pose_history]
            pitches = [pose[1] for pose in self.head_pose_history]

            # Filtrar outliers
            yaws = [y for y in yaws if abs(y) < 60]
            pitches = [p for p in pitches if abs(p) < 45]

            if len(yaws) < 10 or len(pitches) < 10:
                return 0.0, 'insufficient_valid_data'

            yaw_variance = np.var(yaws)
            pitch_variance = np.var(pitches)
            combined_variance = (yaw_variance + pitch_variance) / 2

            # Umbrales ajustados
            RIGID_THRESHOLD = 3.0
            AGITATED_THRESHOLD = 80.0

            if combined_variance < RIGID_THRESHOLD:
                return combined_variance, 'rigid'
            elif combined_variance > AGITATED_THRESHOLD:
                return combined_variance, 'agitated'
            else:
                return combined_variance, 'normal'

        except Exception as e:
            logging.error(f"[ERROR] Error analizando estabilidad: {str(e)}")
            return 0.0, 'error'

    # =========================
    # Métodos auxiliares nuevos
    # =========================
    def _get_empty_metrics(self) -> Dict[str, Any]:
        """Retorna métricas vacías con estructura consistente"""
        return {
            'avg_ear': 0.0,
            'focus': 'No detectado',
            'faces': 0,
            'eyes_detected': False,
            'brightness': 0.0,
            'head_yaw': 0.0,
            'head_pitch': 0.0,
            'head_roll': 0.0,
            'mar': 0.0,
            'is_mouth_open': False,
            'is_yawning': False,
            'yawn_count': 0,
            'head_pose_stability': 'insufficient_data',
            'head_pose_variance': 0.0,
            'is_eyes_closed': False,
            'is_microsleep': False
        }

    def _initialize_metrics(self, brightness: float) -> Dict[str, Any]:
        """Inicializa métricas con brillo calculado"""
        metrics = self._get_empty_metrics()
        metrics['brightness'] = brightness
        return metrics

    def _extract_eye_points(self, face_landmarks, frame_shape):
        """Extrae puntos de los ojos de forma segura"""
        left_eye = [[int(face_landmarks.landmark[point].x * frame_shape[1]),
                     int(face_landmarks.landmark[point].y * frame_shape[0])]
                    for point in EyePoints.LEFT_EYE]

        right_eye = [[int(face_landmarks.landmark[point].x * frame_shape[1]),
                      int(face_landmarks.landmark[point].y * frame_shape[0])]
                     for point in EyePoints.RIGHT_EYE]

        return left_eye, right_eye

    def _draw_face_ellipse(self, frame, face_landmarks):
        """Dibuja un óvalo facial con puntos (dotted) y glow suave configurable."""
        # Configuración segura vía getattr para evitar AttributeError si faltan campos
        # Respeta tanto la configuración de usuario como el switch de runtime
        if not getattr(self, 'overlay_runtime_enabled', True):
            return
        enabled = True
        if self.user_config is not None:
            enabled = bool(getattr(self.user_config, 'face_overlay_enabled', True))
        if not enabled:
            return  # Salir sin dibujar si está deshabilitado desde config
        
        try:
            h, w = frame.shape[:2]
            # Recolectar puntos del óvalo facial
            oval_indices = set()
            for a, b in mp_face_mesh.FACEMESH_FACE_OVAL:
                oval_indices.add(a)
                oval_indices.add(b)
            pts = np.array([
                (
                    int(face_landmarks.landmark[i].x * w),
                    int(face_landmarks.landmark[i].y * h)
                ) for i in oval_indices
            ], dtype=np.int32)

            if len(pts) >= 5:
                # Obtener configuración del usuario con defaults robustos
                glow_intensity = 0.6
                blur_sigma = 9
                dot_radius = 3
                dot_color = (0, 255, 128)
                if self.user_config is not None:
                    try:
                        glow_intensity = float(getattr(self.user_config, 'face_overlay_glow_intensity', glow_intensity))
                    except Exception:
                        pass
                    try:
                        blur_sigma = int(getattr(self.user_config, 'face_overlay_blur_sigma', blur_sigma))
                    except Exception:
                        pass
                # Clamp de seguridad
                glow_intensity = max(0.0, min(1.0, glow_intensity))
                blur_sigma = max(1, int(blur_sigma))

                # Calcular envolvente y muestrear puntos espaciados
                hull = cv2.convexHull(pts)
                hull_pts = hull.squeeze()
                if len(hull_pts.shape) == 1:  # caso degenerado
                    hull_pts = pts
                num_points = len(hull_pts)
                step = max(1, num_points // 30)  # ~30 puntos

                # Dibujar en overlay para glow
                overlay = np.zeros_like(frame)
                for i in range(0, num_points, step):
                    px, py = int(hull_pts[i][0]), int(hull_pts[i][1])
                    cv2.circle(overlay, (px, py), dot_radius + 2, dot_color, thickness=-1, lineType=cv2.LINE_AA)

                glow = cv2.GaussianBlur(overlay, ksize=(0, 0), sigmaX=blur_sigma, sigmaY=blur_sigma)
                cv2.addWeighted(glow, glow_intensity, frame, 1.0, 0, dst=frame)

                # Dibujar puntos nítidos encima
                for i in range(0, num_points, step):
                    px, py = int(hull_pts[i][0]), int(hull_pts[i][1])
                    cv2.circle(frame, (px, py), dot_radius, (0, 255, 0), thickness=-1, lineType=cv2.LINE_AA)
        except Exception as draw_e:
            logging.debug(f"[DRAW] No se pudo dibujar elipse facial: {draw_e}")
    
    def detect_blink(self, frame) -> Tuple[bool, Dict[str, Any]]:
        """
        Detecta parpadeos en el frame proporcionado y retorna métricas completas.
        
        Returns:
            Tuple[bool, Dict]: (is_blink, metrics)
        """
        try:
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            # Redimensionar para rendimiento si aplica (coord. normalizadas siguen válidas)
            if self.processing_scale < 1.0:
                resized_rgb = cv2.resize(
                    rgb_frame,
                    (0, 0),
                    fx=float(self.processing_scale),
                    fy=float(self.processing_scale),
                    interpolation=cv2.INTER_AREA
                )
                results = self.face_mesh.process(resized_rgb)
            else:
                results = self.face_mesh.process(rgb_frame)
        except Exception as e:
            print(f"[ERROR] Error procesando frame: {str(e)}")
            metrics = self._get_empty_metrics()
            metrics.update({'focus': 'Error'})
            return False, metrics
        
        # Calcular brillo del frame (siempre, incluso sin rostros)
        brightness = self.calculate_brightness(frame)
        
        metrics = self._initialize_metrics(brightness)
        
        if results.multi_face_landmarks:
            metrics['faces'] = len(results.multi_face_landmarks)
            
            # Si hay múltiples personas, reportarlo inmediatamente
            if len(results.multi_face_landmarks) > 1:
                metrics['focus'] = 'Múltiples personas'
                return False, metrics
            
            try:
                face_landmarks = results.multi_face_landmarks[0]
                
                # ---  ELIPSE SUAVE  ---
                self._draw_face_ellipse(frame, face_landmarks)
                
                # === 1. CÁLCULO DE EAR (Eye Aspect Ratio) ===
                left_eye, right_eye = self._extract_eye_points(face_landmarks, frame.shape)
                
                left_ear = self.calculate_ear(left_eye)
                right_ear = self.calculate_ear(right_eye)
                avg_ear = (left_ear + right_ear) / 2
                metrics['avg_ear'] = avg_ear
                metrics['eyes_detected'] = True
                
                # === 2. CÁLCULO DE HEAD POSE (Pose de Cabeza) ===
                yaw, pitch, roll = self.estimate_head_pose(face_landmarks.landmark, frame.shape)
                metrics['head_yaw'] = yaw
                metrics['head_pitch'] = pitch
                metrics['head_roll'] = roll
                
                # Guardar en historial para análisis de estabilidad
                self.head_pose_history.append((yaw, pitch, roll))
                if len(self.head_pose_history) > self.MAX_POSE_HISTORY:
                    self.head_pose_history.pop(0)
                
                # Analizar estabilidad de pose
                variance, stability_state = self.analyze_head_pose_stability()
                metrics['head_pose_variance'] = variance
                metrics['head_pose_stability'] = stability_state
                
                # === 3. CÁLCULO DE MAR (Mouth Aspect Ratio) ===
                mar = self.calculate_mar(face_landmarks.landmark, frame.shape)
                metrics['mar'] = mar
                
                # Detectar bostezo
                current_time = time.time()
                if mar > self.MAR_YAWN_THRESHOLD:
                    if not self.is_mouth_open:
                        self.mouth_open_time = current_time
                        self.is_mouth_open = True
                        self.yawn_active = False
                    else:
                        mouth_open_duration = current_time - self.mouth_open_time
                        if mouth_open_duration >= self.MIN_YAWN_DURATION:
                            metrics['is_yawning'] = True
                            metrics['yawn_duration'] = mouth_open_duration
                            # Incrementar contador solo una vez por evento, con cooldown
                            time_since_last_yawn = current_time - self.last_yawn_time
                            if (not self.yawn_active) and (time_since_last_yawn > self.yawn_cooldown):
                                self.yawn_counter += 1
                                self.last_yawn_time = current_time
                                self.yawn_active = True
                    metrics['is_mouth_open'] = True
                else:
                    self.is_mouth_open = False
                    self.yawn_active = False
                    metrics['is_mouth_open'] = False
                    metrics['is_yawning'] = False
                
                # Añadir contador de bostezos a las métricas
                metrics['yawn_count'] = self.yawn_counter
                
                # === 4. DETERMINAR FOCUS (basado en HEAD POSE, NO en EAR) ===
                # Persona mirando al frente: yaw y pitch cercanos a 0
                is_looking_forward = (abs(yaw) < self.HEAD_YAW_THRESHOLD and 
                                     abs(pitch) < self.HEAD_PITCH_THRESHOLD)
                
                if is_looking_forward:
                    metrics['focus'] = 'Atento'
                else:
                    # Determinar tipo de distracción
                    if pitch < -self.PHONE_USE_PITCH and abs(yaw) < self.PHONE_USE_YAW:
                        metrics['focus'] = 'Uso de celular'
                    elif abs(yaw) > self.HEAD_YAW_THRESHOLD:
                        metrics['focus'] = 'Mirando a los lados'
                    elif pitch > self.HEAD_PITCH_THRESHOLD:
                        metrics['focus'] = 'Mirando arriba'
                    else:
                        metrics['focus'] = 'Distraído'
                
                # === 5. DETECCIÓN DE PARPADEO ===
                is_blink = False
                if avg_ear < self.EAR_THRESHOLD:
                    if not self.is_eye_closed:
                        self.eye_closed_time = current_time
                        self.is_eye_closed = True
                else:
                    if self.is_eye_closed:
                        blink_duration = current_time - self.eye_closed_time
                        
                        # Detectar microsueño (ojos cerrados por más tiempo del normal)
                        if blink_duration > self.MAX_BLINK_DURATION:
                            metrics['is_microsleep'] = True
                            metrics['microsleep_duration'] = blink_duration
                        elif (self.MIN_BLINK_DURATION <= blink_duration <= self.MAX_BLINK_DURATION and
                              current_time - self.last_blink_time > self.DEBOUNCE_TIME):
                            self.last_blink_time = current_time
                            is_blink = True
                            metrics['blink_duration_ms'] = int(blink_duration * 1000)
                    
                    self.is_eye_closed = False
                
                # Añadir info de ojos cerrados
                metrics['is_eyes_closed'] = self.is_eye_closed
                if self.is_eye_closed:
                    metrics['eyes_closed_duration'] = current_time - self.eye_closed_time
                
                # Logging detallado opcional
                if logging.getLogger().isEnabledFor(logging.DEBUG):
                    try:
                        logging.debug(
                            f"[METRICS] EAR={metrics['avg_ear']:.3f}, MAR={metrics['mar']:.3f}, "
                            f"Yaw={metrics['head_yaw']:.1f}, Pitch={metrics['head_pitch']:.1f}, Focus={metrics['focus']}"
                        )
                    except Exception:
                        pass

                return is_blink, metrics
                
            except Exception as e:
                print(f"[ERROR] Error procesando landmarks: {str(e)}")
                return False, metrics
            
        return False, metrics


class CameraManager:
    """
    Clase para gestionar la cámara y el procesamiento de video.
    Maneja la inicialización, captura de frames, detección de parpadeos y análisis profundo.
    """
    
    def __init__(self, user_config=None, effective_config=None):
        self._internal_lock = threading.Lock()
        self._metrics_lock = threading.Lock()
        self.video = None
        self.is_running = False
        self.is_paused = False
        self.session_id = None
        self.pause_frame = None
        self.pause_metrics = None
        self.latest_metrics = {}
        
        # Almacenar configuración del usuario
        self.user_config = user_config
        # Almacenar configuración efectiva global+usuario
        self.effective_config = effective_config or {}
        
        # Inicializar detector con configuración del usuario
        # 🆕 Usar el sistema unificado
        self.detection_system = UnifiedDetectionSystem(user_config=user_config)
        self.blink_counter = 0
        self.yawn_counter = 0
        self.last_frame_time = 0
        
        # Usar intervalo de muestreo del usuario si está disponible
        if user_config and hasattr(user_config, 'sampling_interval_seconds'):
            self.frame_interval = user_config.sampling_interval_seconds / 30.0
            print(f"[CAMERA] Intervalo de muestreo personalizado: {user_config.sampling_interval_seconds}s")
        else:
            self.frame_interval = 1.0 / 30
        
        # Control de frecuencia de análisis profundo
        if user_config and hasattr(user_config, 'monitoring_frequency'):
            self.analysis_interval = user_config.monitoring_frequency  # segundos
            print(f"[CAMERA] Frecuencia de análisis: cada {self.analysis_interval}s")
        else:
            self.analysis_interval = 30  # default: 30 segundos
        
        self.last_analysis_time = 0  # Timestamp del último análisis profundo
        
        self.error_count = 0
        self.max_errors = 3
        # Contadores de rendimiento
        self.frames_processed = 0
        self.valid_detections = 0
        # Objetivos de rendimiento
        self.target_fps = 15.0
        self.low_fps_threshold = 12.0
        self.min_fps_threshold = 8.0

        # Integración opcional de modelos mejorados basada en effective_config
        self.multi_detector = None
        self.enhanced_config = self.effective_config
        try:
            models_enabled = (
                self.effective_config.get('gaze_tracking_enabled') or
                self.effective_config.get('yawn_cnn_enabled') or
                self.effective_config.get('phone_detection_enabled')
            )
            if models_enabled:
                from .enhanced_detection import MultiModelDetector
                from types import SimpleNamespace
                config_obj = SimpleNamespace(**self.effective_config)
                self.multi_detector = MultiModelDetector(
                    user_config=user_config,
                    enhanced_config=config_obj
                )
                active_models = [k for k, v in self.effective_config.items() if k.endswith('_enabled') and v]
                logging.info(f"[CAMERA] Enhanced models (global) inicializados: {', '.join(active_models)}")
            else:
                logging.info("[CAMERA] Enhanced models (global) deshabilitados")
        except ImportError:
            logging.debug("[CAMERA] enhanced_detection.py no disponible (opcional)")
        except Exception as e:
            logging.warning(f"[CAMERA] Error al inicializar enhanced models (global): {e}")

        def validate_frame_dimensions(self, frame: np.ndarray) -> bool:
            """
            Valida que el frame tenga dimensiones válidas antes de procesar.
            """
            if frame is None:
                logging.error("[CAMERA] Frame es None")
                return False
            if not hasattr(frame, 'shape') or len(frame.shape) < 2:
                logging.error(f"[CAMERA] Frame sin shape válido: {getattr(frame, 'shape', None)}")
                return False
            h, w = frame.shape[:2]
            if h < 10 or w < 10:
                logging.error(f"[CAMERA] Dimensiones inválidas: h={h}, w={w}")
                return False
            return True
        
    def start_camera(self) -> bool:
        """Inicia la cámara con reintentos y configuración optimizada (no bloqueante)"""
        if self.is_running:
            logging.warning("[CAMERA] Intento de iniciar cámara ya activa")
            return True

        try:
            max_retries = 2
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
    
    def should_perform_analysis(self) -> bool:
        """Determina si es momento de hacer análisis profundo basado en monitoring_frequency"""
        current_time = time.time()
        if current_time - self.last_analysis_time >= self.analysis_interval:
            self.last_analysis_time = current_time
            return True
        return False
    
    def perform_deep_analysis(self, metrics: Dict[str, Any]):
        """Realiza análisis más profundo de métricas y guarda snapshots"""
        logging.info(f"[ANALYSIS] Análisis profundo: EAR={metrics.get('avg_ear', 0):.3f}, Focus={metrics.get('focus', 'N/A')}")
        
        if not self.session_id:
            return
        
        try:
            session = MonitorSession.objects.get(id=self.session_id)
            
            # Crear snapshot de métricas actuales
            current_snapshot = {
                'timestamp': timezone.now().isoformat(),
                'avg_ear': metrics.get('avg_ear', 0),
                'focus': metrics.get('focus', 'Unknown'),
                'blink_count': self.blink_counter,
                'faces_detected': metrics.get('faces', 0),
                'eyes_detected': metrics.get('eyes_detected', False)
            }
            
            # Agregar a metadata de sesión
            if session.metadata:
                snapshots = session.metadata.get('analysis_snapshots', [])
            else:
                snapshots = []
            
            snapshots.append(current_snapshot)
            
            # Limitar a últimos 50 snapshots para no sobrecargar
            if len(snapshots) > 50:
                snapshots = snapshots[-50:]
            
            session.metadata = {
                **(session.metadata or {}),
                'analysis_snapshots': snapshots,
                'last_analysis': timezone.now().isoformat()
            }
            session.save(update_fields=['metadata'])
            
            logging.info(f"[ANALYSIS] Snapshot guardado para sesión {self.session_id} (total: {len(snapshots)})")
            
        except MonitorSession.DoesNotExist:
            logging.error(f"[ANALYSIS] Sesión {self.session_id} no encontrada")
        except Exception as e:
            logging.error(f"[ANALYSIS] Error guardando snapshot: {e}")
    
    def get_frame(self) -> Tuple[Optional[np.ndarray], Dict[str, Any]]:
        """Obtiene un frame de la cámara y procesa métricas"""
        current_time = time.time()
        
        # Verificar estado básico sin lock
        if not self.is_running:
            return None, {'error': 'camera_not_running', 'is_running': False}
        
        if not self.video or not self.video.isOpened():
            # Silenciar el warning para evitar spam en consola
            return None, {'error': 'camera_not_initialized', 'is_running': self.is_running}
        
        # Retornar frame pausado si está en pausa
        if self.is_paused:
            if self.pause_frame is not None:
                logging.debug("[CAMERA] Retornando imagen de pausa")
            else:
                logging.warning("[CAMERA] is_paused=True pero pause_frame es None")
            return self.pause_frame, self.pause_metrics or {'status': 'paused'}

        # Control de FPS
        time_since_last_frame = current_time - self.last_frame_time
        if time_since_last_frame < self.frame_interval:
            time.sleep(self.frame_interval - time_since_last_frame)

        try:
            ret, frame = self.video.read()
            if not ret or frame is None:
                self.error_count += 1
                return None, {'error': 'frame_read_error'}

            # Validar dimensiones del frame antes de procesar
            if not self.validate_frame_dimensions(frame):
                self.error_count += 1
                return None, {'error': 'invalid_frame_dimensions'}

            # 🆕 Procesar con sistema unificado
            metrics = self.detection_system.process_frame(frame)

            # Actualizar contadores
            if metrics.get('blink_detected', False):
                self.blink_counter += 1

            # Sincronizar contador de bostezos desde el detector
            self.yawn_counter = self.detection_system.yawn_detector.yawn_counter

            # Agregar métricas adicionales y propagar eyes_detected
            metrics.update({
                'total_blinks': self.blink_counter,
                'total_yawns': self.yawn_counter,
                'yawn_count': self.yawn_counter,
                'fps': 1.0 / (current_time - self.last_frame_time) if self.last_frame_time > 0 else 0,
                'error_count': self.error_count,
                'session_id': self.session_id,
                'eyes_detected': metrics.get('eyes_detected', False)
            })

            # Actualizar métricas con thread safety
            with self._metrics_lock:
                self.latest_metrics = metrics

            self.last_frame_time = time.time()
            self.error_count = 0

            return frame, metrics

        except Exception as e:
            logging.error(f"[CAMERA] Error procesando frame: {str(e)}")
            return None, {'error': f'processing_error: {str(e)}'}

    def _adjust_processing_quality(self, fps: float):
        """Ajusta escala de procesamiento y overlay para balancear precisión y rendimiento."""
        try:
            # Preferimos mantener precisión, pero si el FPS cae mucho, reducimos costo
            if fps < self.min_fps_threshold:
                # Modo agresivo de rendimiento
                self.blink_detector.processing_scale = 0.5  # 50% resolución
                self.blink_detector.overlay_runtime_enabled = False
            elif fps < self.low_fps_threshold:
                # Modo equilibrado
                self.blink_detector.processing_scale = 0.7  # 70% resolución
                # Mantener overlay activado solo si el usuario lo tiene habilitado y no estamos muy lentos
                self.blink_detector.overlay_runtime_enabled = True
                self.blink_detector.processing_scale = 1.0
                self.blink_detector.overlay_runtime_enabled = True
        except Exception as e:
            logging.debug(f"[ADAPT] No se pudo ajustar calidad: {e}")
    
    def handle_camera_error(self):
        logging.error("[CAMERA] Error crítico detectado, intentando reiniciar la cámara")
        try:
            if self.video and self.video.isOpened():
                self.video.release()
            self.video = None
            time.sleep(2)
            
            if self.start_camera():
                logging.info("[CAMERA] Cámara reiniciada exitosamente")
                self.error_count = 0
            else:
                    # 🆕 Procesar con sistema unificado
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

                # Validar que las métricas sean del frame válido
                if not isinstance(metrics, dict):
                    logging.error("[METRICS] latest_metrics no es dict")
                    metrics = {}

                # Validar dimensiones si hay frame
                if 'frame' in metrics and not self.validate_frame_dimensions(metrics['frame']):
                    logging.error("[METRICS] Frame inválido en métricas")
                    metrics = {}

                # Agregar métricas adicionales
                metrics.update({
                    'total_blinks': self.blink_counter,
                    'camera_status': 'running' if self.is_running else 'stopped',
                    'is_paused': self.is_paused,
                    'error_count': self.error_count,
                    'fps': 1.0 / (current_time - self.last_frame_time) if self.last_frame_time > 0 else 0,
                    'system_time': current_time,
                    'uptime': current_time - self.last_frame_time if self.last_frame_time > 0 else 0,
                    'yawn_count': self.yawn_counter,
                    'total_yawns': self.yawn_counter
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
    

    def register_yawn(self):
        """Registra un bostezo alerta (ALERT_YAWN) y actualiza contador."""
        if not self.session_id:
            return
        try:
            session = MonitorSession.objects.get(id=self.session_id)
            
            # Crear evento de alerta
            AlertEvent.objects.create(
                session=session,
                alert_type=AlertEvent.ALERT_YAWN,
                level='medium',
                message='Bostezo detectado',
                timestamp=timezone.now(),
                metadata={}
            )
            
            # 🔥 ACTUALIZAR: Incrementar contador de bostezos en la sesión
            session.total_yawns = (session.total_yawns or 0) + 1
            session.total_alerts = (session.total_alerts or 0) + 1
            session.save(update_fields=['total_yawns', 'total_alerts'])
            
            logging.info(f"[YAWN] Bostezo registrado en BD. Total sesión: {session.total_yawns}")
            
        except MonitorSession.DoesNotExist:
            print(f"[ERROR] Sesión {self.session_id} no encontrada para registrar bostezo")
        except Exception as e:
            print(f"[ERROR] Error al registrar bostezo: {str(e)}")
