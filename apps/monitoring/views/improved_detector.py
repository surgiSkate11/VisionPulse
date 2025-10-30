import cv2
import numpy as np
import mediapipe as mp
from scipy.spatial import distance as dist
from collections import deque
import time
import logging
from typing import Tuple, Optional, Dict, Any

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ImprovedBlinkDetector:
    def __init__(self, ear_threshold=0.21, consecutive_frames=2):
        self.EAR_THRESHOLD = ear_threshold
        self.CONSECUTIVE_FRAMES = consecutive_frames
        self.ear_history = deque(maxlen=5)
        self.frame_counter = 0
        self.blink_counter = 0
        self.last_blink_time = 0
        self.is_blinking = False
        self.LEFT_EYE_IDXS = [33, 160, 158, 133, 153, 144]
        self.RIGHT_EYE_IDXS = [362, 385, 387, 263, 373, 380]
        logger.info(f"[BLINK] Inicializado con EAR={ear_threshold}, frames={consecutive_frames}")
    
    def calculate_ear(self, eye_points: np.ndarray) -> float:
        try:
            A = dist.euclidean(eye_points[1], eye_points[5])
            B = dist.euclidean(eye_points[2], eye_points[4])
            C = dist.euclidean(eye_points[0], eye_points[3])
            # Validación robusta para evitar división por cero
            if C < 0.1:
                logging.debug(f"[EAR] División por cero evitada: C={C}")
                return 0.0
            ear = (A + B) / (2.0 * C)
            return float(ear)
        except Exception as e:
            logging.error(f"[EAR] Error en cálculo: {e}")
            return 0.0
    
    def extract_eye_points(self, landmarks, indices, frame_shape) -> np.ndarray:
        h, w = frame_shape[:2]
        points = np.array([
            [int(landmarks.landmark[idx].x * w), int(landmarks.landmark[idx].y * h)]
            for idx in indices
        ])
        return points
    
    def validate_eye_visibility(self, eye_points: np.ndarray) -> bool:
        area = cv2.contourArea(eye_points)
        width = dist.euclidean(eye_points[0], eye_points[3])
        min_area = 50
        min_width = 15
        is_visible = (area > min_area and width > min_width)
        return is_visible
    
    def detect(self, face_landmarks, frame_shape) -> Tuple[bool, float, Dict[str, Any]]:
        left_eye = self.extract_eye_points(face_landmarks, self.LEFT_EYE_IDXS, frame_shape)
        right_eye = self.extract_eye_points(face_landmarks, self.RIGHT_EYE_IDXS, frame_shape)
        left_visible = self.validate_eye_visibility(left_eye)
        right_visible = self.validate_eye_visibility(right_eye)
        eyes_properly_detected = left_visible and right_visible
        if eyes_properly_detected:
            left_ear = self.calculate_ear(left_eye)
            right_ear = self.calculate_ear(right_eye)
            avg_ear = (left_ear + right_ear) / 2.0
            if not (0.1 < avg_ear < 0.4):
                eyes_properly_detected = False
                avg_ear = 0.0
        else:
            avg_ear = 0.0
            left_ear = 0.0
            right_ear = 0.0
        self.ear_history.append(avg_ear)
        smoothed_ear = np.mean(self.ear_history)
        is_blink = False
        if eyes_properly_detected:
            if smoothed_ear < self.EAR_THRESHOLD:
                self.frame_counter += 1
                if self.frame_counter >= self.CONSECUTIVE_FRAMES and not self.is_blinking:
                    self.blink_counter += 1
                    self.is_blinking = True
                    is_blink = True
                    self.last_blink_time = time.time()
                    logger.debug(f"[BLINK] Detectado #{self.blink_counter} | EAR={smoothed_ear:.3f}")
            else:
                self.frame_counter = 0
                self.is_blinking = False
        else:
            self.frame_counter = 0
            self.is_blinking = False
        metrics = {
            'avg_ear': avg_ear,
            'smoothed_ear': smoothed_ear,
            'left_ear': left_ear,
            'right_ear': right_ear,
            'total_blinks': self.blink_counter,
            'frames_closed': self.frame_counter,
            'eyes_detected': eyes_properly_detected,
            'left_eye_visible': left_visible,
            'right_eye_visible': right_visible
        }
        return is_blink, smoothed_ear, metrics

class ImprovedYawnDetector:
    def __init__(self, mar_threshold=0.50, min_duration=0.8):
        self.MAR_THRESHOLD = mar_threshold
        self.MIN_DURATION = min_duration
        self.is_mouth_open = False
        self.mouth_open_start = 0
        self.yawn_counter = 0
        self.last_yawn_time = 0
        self.cooldown = 1.5
        self.mar_history = deque(maxlen=5)
        self.MOUTH_POINTS = {
            'vertical_top': 13,
            'vertical_bottom': 14,
            'left_corner': 61,
            'right_corner': 291
        }
        logger.info(f"[YAWN] Inicializado con MAR={mar_threshold}, duration={min_duration}s")
    def calculate_mar(self, landmarks, frame_shape) -> float:
        h, w = frame_shape[:2]
        top = landmarks.landmark[self.MOUTH_POINTS['vertical_top']]
        bottom = landmarks.landmark[self.MOUTH_POINTS['vertical_bottom']]
        left = landmarks.landmark[self.MOUTH_POINTS['left_corner']]
        right = landmarks.landmark[self.MOUTH_POINTS['right_corner']]
        top_y = int(top.y * h)
        bottom_y = int(bottom.y * h)
        left_x = int(left.x * w)
        right_x = int(right.x * w)
        height = abs(bottom_y - top_y)
        width = abs(right_x - left_x)
        # Validación robusta para evitar división por cero
        if width < 1:
            logging.debug(f"[MAR] División por cero evitada: width={width}")
            return 0.0
        mar = height / width
        mar = max(0.0, min(mar, 2.0))
        return float(mar)
    def detect(self, face_landmarks, frame_shape) -> Tuple[bool, float, Dict[str, Any]]:
        current_time = time.time()
        mar = self.calculate_mar(face_landmarks, frame_shape)
        self.mar_history.append(mar)
        smoothed_mar = np.mean(self.mar_history)
        is_yawning = False
        yawn_duration = 0
        if smoothed_mar > self.MAR_THRESHOLD:
            if not self.is_mouth_open:
                self.mouth_open_start = current_time
                self.is_mouth_open = True
                logger.debug(f"[YAWN] Boca abierta | MAR={smoothed_mar:.3f}")
            else:
                yawn_duration = current_time - self.mouth_open_start
                time_since_last = current_time - self.last_yawn_time
                if (yawn_duration >= self.MIN_DURATION and time_since_last > self.cooldown):
                    self.yawn_counter += 1
                    self.last_yawn_time = current_time
                    is_yawning = True
                    logger.info(f"[YAWN] ¡Detectado #{self.yawn_counter}! | MAR={smoothed_mar:.3f} | Duration={yawn_duration:.1f}s")
        else:
            if smoothed_mar < (self.MAR_THRESHOLD * 0.8):
                self.is_mouth_open = False
                self.mouth_open_start = 0
        metrics = {
            'mar': mar,
            'smoothed_mar': smoothed_mar,
            'is_mouth_open': self.is_mouth_open,
            'mouth_open_duration': yawn_duration,
            'total_yawns': self.yawn_counter,
            'is_yawning': is_yawning
        }
        return is_yawning, smoothed_mar, metrics

class ImprovedPhoneDetector:
    def __init__(self):
        try:
            from ultralytics import YOLO
            self.model = YOLO('yolov8n.pt')
            self.available = True
            logger.info("[PHONE] YOLOv8 cargado correctamente")
        except Exception as e:
            logger.warning(f"[PHONE] YOLO no disponible: {e}")
            self.available = False
            self.model = None
        self.PHONE_CLASS_ID = 67
        self.CONFIDENCE_THRESHOLD = 0.5
        self.PHONE_PITCH_MIN = -35
        self.PHONE_YAW_MAX = 20
    def detect(self, frame: np.ndarray, head_pitch: float, head_yaw: float, eyes_detected: bool = True) -> Tuple[bool, float, Dict[str, Any]]:
        phone_detected = False
        phone_confidence = 0.0
        phone_bbox = None
        if self.available and self.model is not None:
            try:
                results = self.model(frame, verbose=False, conf=self.CONFIDENCE_THRESHOLD)
                for result in results:
                    boxes = result.boxes
                    for box in boxes:
                        class_id = int(box.cls[0])
                        if class_id == self.PHONE_CLASS_ID:
                            phone_detected = True
                            phone_confidence = float(box.conf[0])
                            phone_bbox = box.xyxy[0].tolist()
                            break
                    if phone_detected:
                        break
            except Exception as e:
                logger.error(f"[PHONE] Error en detección YOLO: {e}")
        typical_phone_pose = (
            head_pitch < self.PHONE_PITCH_MIN and abs(head_yaw) < self.PHONE_YAW_MAX
        )
        final_confidence = 0.0
        detection_method = "none"
        if phone_detected and typical_phone_pose:
            final_confidence = min(0.95, phone_confidence + 0.2)
            detection_method = "object+pose"
        elif phone_detected:
            final_confidence = phone_confidence
            detection_method = "object_only"
        elif typical_phone_pose and not eyes_detected:
            final_confidence = 0.7
            detection_method = "pose_only"
        elif typical_phone_pose and eyes_detected:
            final_confidence = 0.3
            detection_method = "pose_uncertain"
        is_using_phone = final_confidence >= 0.65
        metadata = {
            'phone_detected': phone_detected,
            'phone_confidence': phone_confidence,
            'phone_bbox': phone_bbox,
            'head_pitch': head_pitch,
            'head_yaw': head_yaw,
            'eyes_detected': eyes_detected,
            'typical_pose': typical_phone_pose,
            'detection_method': detection_method,
            'final_confidence': final_confidence
        }
        if is_using_phone:
            logger.info(f"[PHONE] Uso detectado | Método={detection_method} | Conf={final_confidence:.2f}")
        return is_using_phone, final_confidence, metadata

class ImprovedFocusDetector:
    def __init__(self):
        self.YAW_THRESHOLD = 20
        self.PITCH_THRESHOLD = 15
        self.focus_history = deque(maxlen=30)
        logger.info("[FOCUS] Inicializado con thresholds adaptativos")
    def estimate_head_pose(self, face_landmarks, frame_shape) -> Tuple[float, float, float]:
        h, w = frame_shape[:2]
        nose_tip = face_landmarks.landmark[1]
        chin = face_landmarks.landmark[152]
        left_eye = face_landmarks.landmark[33]
        right_eye = face_landmarks.landmark[263]
        nose_2d = np.array([nose_tip.x * w, nose_tip.y * h])
        chin_2d = np.array([chin.x * w, chin.y * h])
        left_eye_2d = np.array([left_eye.x * w, left_eye.y * h])
        right_eye_2d = np.array([right_eye.x * w, right_eye.y * h])
        eye_center_x = (left_eye_2d[0] + right_eye_2d[0]) / 2
        nose_offset_x = nose_2d[0] - eye_center_x
        face_width = abs(right_eye_2d[0] - left_eye_2d[0])
        # Validación robusta para evitar división por cero
        if face_width < 1.0:
            logging.debug(f"[POSE] División por cero evitada: face_width={face_width}")
            yaw = 0.0
        else:
            yaw = (nose_offset_x / face_width) * 90
        yaw = np.clip(yaw, -45, 45)
        eye_center_y = (left_eye_2d[1] + right_eye_2d[1]) / 2
        nose_offset_y = nose_2d[1] - eye_center_y
        face_height = abs(chin_2d[1] - eye_center_y)
        if face_height < 1.0:
            logging.debug(f"[POSE] División por cero evitada: face_height={face_height}")
            pitch = 0.0
        else:
            pitch = -(nose_offset_y / face_height) * 60
        pitch = np.clip(pitch, -30, 30)
        delta_y = right_eye_2d[1] - left_eye_2d[1]
        delta_x = right_eye_2d[0] - left_eye_2d[0]
        if abs(delta_x) < 0.1:
            logging.debug(f"[POSE] División por cero evitada: delta_x={delta_x}")
            roll = 0.0
        else:
            roll = np.degrees(np.arctan2(delta_y, delta_x))
        roll = np.clip(roll, -45, 45)
        return float(yaw), float(pitch), float(roll)
    def detect(self, face_landmarks, frame_shape, eyes_detected: bool = True) -> Dict[str, Any]:
        yaw, pitch, roll = self.estimate_head_pose(face_landmarks, frame_shape)
        is_focused = (
            abs(yaw) < self.YAW_THRESHOLD and abs(pitch) < self.PITCH_THRESHOLD and eyes_detected
        )
        self.focus_history.append(1 if is_focused else 0)
        focus_score = (sum(self.focus_history) / len(self.focus_history)) * 100
        if not eyes_detected:
            focus_state = "Cara tapada"
        elif is_focused:
            focus_state = "Atento"
        elif pitch < -25 and not eyes_detected:
            focus_state = "Uso de celular"
        elif abs(yaw) > self.YAW_THRESHOLD:
            focus_state = "Mirando a los lados"
        elif pitch > self.PITCH_THRESHOLD:
            focus_state = "Mirando arriba"
        elif pitch < -self.PITCH_THRESHOLD:
            focus_state = "Mirando abajo"
        else:
            focus_state = "Distraído"
        metrics = {
            'head_yaw': yaw,
            'head_pitch': pitch,
            'head_roll': roll,
            'is_focused': is_focused,
            'focus_state': focus_state,
            'focus_score': focus_score,
            'eyes_visible': eyes_detected
        }
        return metrics

class UnifiedDetectionSystem:
    def __init__(self, user_config=None):
        self.mp_face_mesh = mp.solutions.face_mesh
        self.user_config = user_config
        if user_config:
            ear_threshold = getattr(user_config, 'ear_threshold', 0.21)
            mar_threshold = getattr(user_config, 'yawn_mar_threshold', 0.50)
        else:
            ear_threshold = 0.21
            mar_threshold = 0.50
        self.face_mesh = mp.solutions.face_mesh.FaceMesh(
            static_image_mode=False,
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.7,
            min_tracking_confidence=0.7
        )
        self.blink_detector = ImprovedBlinkDetector(ear_threshold=ear_threshold)
        self.yawn_detector = ImprovedYawnDetector(mar_threshold=mar_threshold)
        self.phone_detector = ImprovedPhoneDetector()
        self.focus_detector = ImprovedFocusDetector()
        logger.info("[SYSTEM] Sistema unificado inicializado correctamente")
    def _draw_face_oval(self, frame: np.ndarray, face_landmarks) -> None:
        try:
            overlay_enabled = True
            if hasattr(self, 'user_config') and self.user_config:
                overlay_enabled = getattr(self.user_config, 'face_overlay_enabled', True)
            if not overlay_enabled:
                return
            h, w = frame.shape[:2]
            oval_indices = set()
            for connection in self.mp_face_mesh.FACEMESH_FACE_OVAL:
                oval_indices.add(connection[0])
                oval_indices.add(connection[1])
            pts = np.array([
                (int(face_landmarks.landmark[i].x * w), int(face_landmarks.landmark[i].y * h))
                for i in oval_indices
            ], dtype=np.int32)
            if len(pts) < 5:
                return
            glow_intensity = 0.6
            blur_sigma = 9
            dot_radius = 3
            dot_color = (0, 255, 128)
            if hasattr(self, 'user_config') and self.user_config:
                glow_intensity = float(getattr(self.user_config, 'face_overlay_glow_intensity', 0.6))
                blur_sigma = int(getattr(self.user_config, 'face_overlay_blur_sigma', 9))
            glow_intensity = max(0.0, min(1.0, glow_intensity))
            blur_sigma = max(1, blur_sigma)
            hull = cv2.convexHull(pts)
            hull_pts = hull.squeeze()
            if len(hull_pts.shape) == 1:
                hull_pts = pts
            num_points = len(hull_pts)
            step = max(1, num_points // 30)
            overlay = np.zeros_like(frame)
            for i in range(0, num_points, step):
                px, py = int(hull_pts[i][0]), int(hull_pts[i][1])
                cv2.circle(overlay, (px, py), dot_radius + 2, dot_color, thickness=-1, lineType=cv2.LINE_AA)
            glow = cv2.GaussianBlur(overlay, ksize=(0, 0), sigmaX=blur_sigma, sigmaY=blur_sigma)
            cv2.addWeighted(glow, glow_intensity, frame, 1.0, 0, dst=frame)
            for i in range(0, num_points, step):
                px, py = int(hull_pts[i][0]), int(hull_pts[i][1])
                cv2.circle(frame, (px, py), dot_radius, (0, 255, 0), thickness=-1, lineType=cv2.LINE_AA)
        except Exception as e:
            logger.debug(f"[DRAW] Error dibujando óvalo: {e}")
    def process_frame(self, frame: np.ndarray) -> Dict[str, Any]:
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.face_mesh.process(rgb_frame)
        metrics = {
            'face_detected': False,
            'eyes_detected': False,
            'blink_detected': False,
            'yawn_detected': False,
            'phone_detected': False,
            'avg_ear': 0.0,
            'mar': 0.0,
            'total_blinks': 0,
            'total_yawns': 0,
            'yawn_count': 0,
            'focus_state': 'No detectado',
            'focus': 'No detectado',
            'focus_score': 0.0,
            'head_yaw': 0.0,
            'head_pitch': 0.0,
            'head_roll': 0.0,
            'faces': 0,
            'is_yawning': False
        }
        if not results.multi_face_landmarks:
            return metrics
        face_landmarks = results.multi_face_landmarks[0]
        frame_shape = frame.shape
        metrics['face_detected'] = True
        metrics['faces'] = 1
        self._draw_face_oval(frame, face_landmarks)
        try:
            is_blink, avg_ear, blink_metrics = self.blink_detector.detect(
                face_landmarks, frame_shape
            )
            eyes_detected = blink_metrics['eyes_detected']
            metrics.update({
                'blink_detected': is_blink,
                'avg_ear': blink_metrics['smoothed_ear'],
                'total_blinks': blink_metrics['total_blinks'],
                'eyes_detected': eyes_detected
            })
            is_yawn, mar, yawn_metrics = self.yawn_detector.detect(
                face_landmarks, frame_shape
            )
            metrics.update({
                'yawn_detected': is_yawn,
                'mar': yawn_metrics['smoothed_mar'],
                'total_yawns': yawn_metrics['total_yawns'],
                'yawn_count': yawn_metrics['total_yawns'],
                'is_yawning': yawn_metrics['is_yawning'],
                'is_mouth_open': yawn_metrics['is_mouth_open'],
                'mouth_open_duration': yawn_metrics.get('mouth_open_duration', 0)
            })
            if yawn_metrics['is_mouth_open']:
                logger.debug(f"[YAWN] Boca abierta | MAR={yawn_metrics['smoothed_mar']:.3f} | "
                           f"Duration={yawn_metrics.get('mouth_open_duration', 0):.1f}s")
            focus_metrics = self.focus_detector.detect(
                face_landmarks, frame_shape, eyes_detected=eyes_detected
            )
            metrics.update(focus_metrics)
            metrics['focus'] = focus_metrics['focus_state']
            is_phone, phone_conf, phone_metadata = self.phone_detector.detect(
                frame,
                metrics['head_pitch'],
                metrics['head_yaw'],
                eyes_detected=eyes_detected
            )
            metrics.update({
                'phone_detected': is_phone,
                'is_using_phone': is_phone,
                'phone_confidence': phone_conf,
                'phone_metadata': phone_metadata
            })
            if is_phone and phone_conf > 0.75:
                metrics['focus_state'] = 'Uso de celular'
                metrics['focus'] = 'Uso de celular'
        except Exception as e:
            logger.error(f"[SYSTEM] Error procesando frame: {e}")
        return metrics
    def release(self):
        self.face_mesh.close()
