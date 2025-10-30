"""
Sistema de detección mejorado con múltiples modelos especializados (opcional).

Este módulo integra:
- L2CS-Net (gaze tracking) si está disponible
- YOLOv8 (detección de celular) si está disponible
- TensorFlow (CNN de bostezos) si está disponible

Todos los imports son opcionales, con fallbacks seguros para no romper el runtime.
"""

from typing import Tuple, Dict, Any, Optional
import logging
import os

import cv2
import numpy as np

# Importar modelos especializados 
try:
    from l2cs import Pipeline as GazePipeline  # type: ignore
    GAZE_AVAILABLE = True
except Exception:
    GAZE_AVAILABLE = False
    from ultralytics import YOLO  # type: ignore
    YOLO_AVAILABLE = True
except Exception:
    YOLO_AVAILABLE = False
    logging.warning("[ENHANCED] YOLO no disponible. Detección de celular limitada.")

try:
    import tensorflow as tf  # type: ignore
    TF_AVAILABLE = True
except Exception:
    TF_AVAILABLE = False
    logging.warning("[ENHANCED] TensorFlow no disponible. Detección de bostezos básica.")


class EnhancedGazeDetector:
    """Detector de mirada mejorado usando L2CS-Net (opcional)."""

    def __init__(self):
        self.available = GAZE_AVAILABLE
        self.gaze_pipeline = None
        if self.available:
            try:
                # Cargar pesos de manera perezosa; el archivo debe existir
                weights = os.environ.get('L2CS_WEIGHTS', 'L2CSNet_gaze360.pkl')
                self.gaze_pipeline = GazePipeline(
                    weights=weights,
                    arch='ResNet50',
                    device='cpu'  # Cambiar a 'cuda' si hay GPU
                )
                logging.info("[GAZE] L2CS-Net cargado correctamente")
            except Exception as e:
                logging.error(f"[GAZE] Error al cargar L2CS: {e}")
                self.available = False

    def estimate_gaze(self, frame: np.ndarray, face_box: Tuple[int, int, int, int]) -> Tuple[Optional[float], Optional[float]]:
        if not self.available or self.gaze_pipeline is None:
            return None, None
        try:
            x1, y1, x2, y2 = face_box
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(frame.shape[1], x2), min(frame.shape[0], y2)
            if x2 <= x1 or y2 <= y1:
                return None, None
            face_img = frame[y1:y2, x1:x2]
            results = self.gaze_pipeline.step(face_img)
            return float(results.yaw), float(results.pitch)
        except Exception as e:
            logging.error(f"[GAZE] Error en estimación: {e}")
            return None, None

    @staticmethod
    def is_looking_at_screen(gaze_yaw: Optional[float], gaze_pitch: Optional[float], ty: float = 15, tp: float = 15) -> bool:
        if gaze_yaw is None or gaze_pitch is None:
            return False
        return abs(gaze_yaw) < ty and abs(gaze_pitch) < tp


class EnhancedYawnDetector:
    """Detector de bostezos con CNN (opcional)."""

    def __init__(self, model_path: Optional[str] = None):
        self.available = TF_AVAILABLE
        self.model = None
        if self.available and model_path and os.path.exists(model_path):
            try:
                self.model = tf.keras.models.load_model(model_path)
                logging.info("[YAWN] Modelo CNN cargado correctamente")
            except Exception as e:
                logging.error(f"[YAWN] Error al cargar modelo: {e}")
                self.available = False

    def detect_yawn_cnn(self, mouth_region: np.ndarray) -> Tuple[bool, float]:
        if not self.available or self.model is None:
            return False, 0.0
        try:
            mouth_resized = cv2.resize(mouth_region, (64, 64))
            mouth_normalized = mouth_resized / 255.0
            batch = np.expand_dims(mouth_normalized, axis=0)
            pred = self.model.predict(batch, verbose=0)
            confidence = float(pred[0][0])
            return confidence > 0.7, confidence
        except Exception as e:
            logging.error(f"[YAWN] Error en predicción CNN: {e}")
            return False, 0.0

    @staticmethod
    def extract_mouth_region(frame: np.ndarray, landmarks) -> Optional[np.ndarray]:
        try:
            h, w = frame.shape[:2]
            # Conjunto amplio de puntos de la boca (MediaPipe)
            mouth_points = [61, 185, 40, 39, 37, 0, 267, 269, 270, 409, 291,
                            146, 91, 181, 84, 17, 314, 405, 321, 375]
            coords = np.array([
                [int(landmarks.landmark[i].x """ * """ w), int(landmarks.landmark[i].y * h)]
                for i in mouth_points
            ])
            x_min, y_min = coords.min(axis=0)
            x_max, y_max = coords.max(axis=0)
            margin = 10
            x_min = max(0, x_min - margin)
            y_min = max(0, y_min - margin)
            x_max = min(w, x_max + margin)
            y_max = min(h, y_max + margin)
            if x_max <= x_min or y_max <= y_min:
                return None
            return frame[y_min:y_max, x_min:x_max]
        except Exception as e:
            logging.error(f"[YAWN] Error extrayendo ROI: {e}")
            return None


class EnhancedPhoneDetector:
    """Detector de uso de celular con YOLO + heurísticas (opcional)."""

    def __init__(self, model_name: str = 'yolov8n.pt', conf_threshold: float = 0.6):
        self.available = YOLO_AVAILABLE
        self.model = None
        self.phone_class_ids = [67]  # COCO 'cell phone'
        self.model_name = model_name
        self.conf_threshold = conf_threshold
        if self.available:
            try:
                self.model = YOLO(self.model_name)  # liviano por defecto
                logging.info(f"[PHONE] YOLOv8 cargado correctamente ({self.model_name})")
            except Exception as e:
                logging.error(f"[PHONE] Error al cargar YOLO: {e}")
                self.available = False

    def detect_phone(self, frame: np.ndarray, head_pitch: float, head_yaw: float) -> Tuple[bool, float, Dict[str, Any]]:
        phone_in_frame = False
        phone_confidence = 0.0
        phone_bbox = None
        if self.available and self.model is not None:
            try:
                results = self.model(frame, verbose=False)
                for box in results[0].boxes:
                    if int(box.cls) in self.phone_class_ids:
                        phone_in_frame = True
                        phone_confidence = float(box.conf)
                        phone_bbox = box.xyxy[0].tolist()
                        break
            except Exception as e:
                logging.error(f"[PHONE] Error en detección YOLO: {e}")
        # Heurística de postura
        typical_phone_pose = (head_pitch < -20 and abs(head_yaw) < 20)
        final_conf = 0.0
        method = "none"
        if phone_in_frame and typical_phone_pose:
            final_conf = 0.95
            method = "object+pose"
        elif phone_in_frame:
            final_conf = 0.75
            method = "object_only"
        elif typical_phone_pose:
            final_conf = 0.45
            method = "pose_only"
        # Umbral configurable
        is_using = final_conf >= self.conf_threshold
        meta = {
            'phone_detected': phone_in_frame,
            'phone_confidence': phone_confidence,
            'phone_bbox': phone_bbox,
            'head_pitch': head_pitch,
            'head_yaw': head_yaw,
            'typical_pose': typical_phone_pose,
            'detection_method': method
        }
        return is_using, final_conf, meta


class MultiModelDetector:
    """Integración de detectores mejorados (opcional)."""

    def __init__(self, user_config=None, enhanced_config=None, yawn_model_path: Optional[str] = None):
        import mediapipe as mp  # dependencia existente
        self.user_config = user_config
        self.enhanced_config = enhanced_config
        
        # Inicializar solo los modelos habilitados en la configuración
        if enhanced_config:
            # Usar configuración específica para cada modelo
            self.gaze_detector = EnhancedGazeDetector() if enhanced_config.gaze_tracking_enabled else None
            self.yawn_detector = EnhancedYawnDetector(
                model_path=enhanced_config.yawn_cnn_model_path if enhanced_config.yawn_cnn_model_path else yawn_model_path
            ) if enhanced_config.yawn_cnn_enabled else None
            self.phone_detector = EnhancedPhoneDetector(
                model_name=(enhanced_config.phone_yolo_model if enhanced_config.phone_yolo_model else 'yolov8n.pt'),
                conf_threshold=(enhanced_config.phone_confidence_threshold if hasattr(enhanced_config, 'phone_confidence_threshold') and enhanced_config.phone_confidence_threshold else 0.6)
            ) if enhanced_config.phone_detection_enabled else None
        else:
            # Fallback a inicializar todos los modelos (retrocompatibilidad)
            self.gaze_detector = EnhancedGazeDetector()
            self.yawn_detector = EnhancedYawnDetector(model_path=yawn_model_path)
            self.phone_detector = EnhancedPhoneDetector()
        
        self.face_mesh = mp.solutions.face_mesh.FaceMesh(
            static_image_mode=False,
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.7,
            min_tracking_confidence=0.7
        )
        logging.info("[MULTI-MODEL] Inicializado | Gaze:%s YawnCNN:%s PhoneYOLO:%s",
                     '✓' if self.gaze_detector and self.gaze_detector.available else '✗',
                     '✓' if self.yawn_detector and self.yawn_detector.available and self.yawn_detector.model is not None else '✗',
                     '✓' if self.phone_detector and self.phone_detector.available else '✗')

    def analyze_frame(self, frame: np.ndarray) -> Dict[str, Any]:
        results: Dict[str, Any] = {
            'face_detected': False,
            'is_focused_gaze': False,
            'is_yawning_cnn': False,
            'is_using_phone': False,
            'gaze_yaw': None,
            'gaze_pitch': None,
            'head_yaw_est': None,
            'head_pitch_est': None,
            'yawn_confidence': 0.0,
            'phone_confidence': 0.0,
            'phone_metadata': {}
        }
        try:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_res = self.face_mesh.process(rgb)
            if not mp_res.multi_face_landmarks:
                return results
            results['face_detected'] = True
            landmarks = mp_res.multi_face_landmarks[0]
            h, w = frame.shape[:2]
            pts = np.array([[int(lm.x * w), int(lm.y * h)] for lm in landmarks.landmark])
            x_min, y_min = pts.min(axis=0)
            x_max, y_max = pts.max(axis=0)

            # Gaze
            if self.gaze_detector and self.gaze_detector.available:
                gyaw, gpitch = self.gaze_detector.estimate_gaze(frame, (x_min, y_min, x_max, y_max))
                results['gaze_yaw'] = gyaw
                results['gaze_pitch'] = gpitch
                results['is_focused_gaze'] = self.gaze_detector.is_looking_at_screen(gyaw, gpitch)

            # Yawn CNN
            if self.yawn_detector and self.yawn_detector.available and self.yawn_detector.model is not None:
                mouth = self.yawn_detector.extract_mouth_region(frame, landmarks)
                if mouth is not None:
                    is_yawn, conf = self.yawn_detector.detect_yawn_cnn(mouth)
                    results['is_yawning_cnn'] = is_yawn
                    results['yawn_confidence'] = conf

            # Phone YOLO (+ pose heurística usa gaze si disponible)
            if self.phone_detector:
                head_yaw = results.get('gaze_yaw') or 0.0
                head_pitch = results.get('gaze_pitch') or 0.0
                is_phone, phone_conf, meta = self.phone_detector.detect_phone(frame, head_pitch, head_yaw)
                results['is_using_phone'] = is_phone
                results['phone_confidence'] = phone_conf
                results['phone_metadata'] = meta

            return results
        except Exception as e:
            logging.error(f"[MULTI-MODEL] Error analizando frame: {e}")
            return results
