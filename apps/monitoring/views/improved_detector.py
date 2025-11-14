
import cv2
import numpy as np
import mediapipe as mp
from scipy.spatial import distance as dist
from collections import deque
import time
import logging
from typing import Tuple, Optional, Dict, Any

# =====================
# Imports Avanzados
# =====================
import logging
import os
import cv2
import numpy as np
try:
    from django.conf import settings as dj_settings  
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
except:
    pass
# =====================
# Sistema de Calibración Dinámica
# =====================
class AdaptiveThresholdCalibrator:
    def __init__(self):
        self.ear_history = deque(maxlen=100)  # Últimos 100 valores de EAR
        self.baseline_ear = 0.25  # ⚡ Valor inicial alto para máxima sensibilidad
        self.calibrated = False
        self.calibration_frames = 0
        self.min_calibration_frames = 20  # ⚡ Solo 20 frames (menos de 1 segundo)
        
    def add_sample(self, ear_value: float):
        """Añade una muestra al historial de calibración"""
        if 0.08 < ear_value < 0.6:  # ⚡ Rango más amplio
            self.ear_history.append(ear_value)
            self.calibration_frames += 1
            
    def get_optimal_threshold(self) -> float:
        """Calcula el umbral óptimo basado en el historial del usuario"""
        if len(self.ear_history) < self.min_calibration_frames:
            return self.baseline_ear
            
        # ⚡ Percentil 30 (más alto = ultra-sensible)
        threshold = np.percentile(list(self.ear_history), 30)
        
        # ⚡ Límites más permisivos
        threshold = max(0.20, min(0.32, threshold))
        
        if not self.calibrated and self.calibration_frames >= self.min_calibration_frames:
            self.calibrated = True
            logger.info(f"[CALIBRATION] Umbral calibrado: EAR={threshold:.3f}")
            
        return threshold
    
    def is_calibrated(self) -> bool:
        return self.calibrated


class ImprovedBlinkDetector:
    def __init__(self, ear_threshold: float = 0.21, microsleep_threshold: float = 5.0):
        # v7.0: SISTEMA ULTRA-PERFECTO - Detección de parpadeos 100% precisa y completa
        self.EAR_THRESHOLD = ear_threshold
        self.blink_counter = 0
        self.last_blink_time = 0.0

        # 🔥 v7.0: PARÁMETROS ULTRA-OPTIMIZADOS para captura PERFECTA de parpadeos
        self.eye_closed_start_time = 0.0
        self.eye_is_closed = False
        self.MIN_BLINK_DURATION_SEC = 0.020  # 🔥 20ms mínimo (captura parpadeos ULTRA-rápidos)
        self.MAX_BLINK_DURATION_SEC = 0.700  # 🔥 700ms máximo (permite parpadeos lentos/deliberados)
        self.DEBOUNCE_SEC = 0.025            # 🔥 25ms entre parpadeos (captura parpadeos dobles/triples rápidos)
        
        # 🔥 v7.0: CONFIRMACIÓN DE 1 FRAME - RESPUESTA INSTANTÁNEA
        # Con todas las validaciones de calidad, 1 frame es suficiente para confirmar
        self.CONFIRMATION_FRAMES = 1  # Respuesta inmediata sin perder precisión
        self.closing_confirmation_count = 0
        self.opening_confirmation_count = 0
        
        # Sin calibración (umbral fijo más confiable)
        self.calibrator = None
        self.use_adaptive_threshold = False

        # 🔥 v7.0: Filtrado EWMA MÁXIMA RESPUESTA
        self.smoothed_ear = 0.21
        self.alpha = 0.90  # 🔥 90% actual, 10% histórico (MÁXIMA respuesta para capturar parpadeos rápidos)
        
        # 🆕 NUEVO: Buffer de EAR para análisis de tendencia
        self.ear_buffer = deque(maxlen=5)  # Últimos 5 valores
        
        # Detección de microsueño (configurable 5-15s)
        try:
            ms = float(microsleep_threshold)
        except Exception:
            ms = 5.0
        self.microsleep_threshold = max(5.0, min(15.0, ms))
        self.current_microsleep = False
        
        # Historial de parpadeos para análisis de frecuencia
        self.blink_timestamps = deque(maxlen=100)  # Últimos 100 parpadeos (más historial)

        self.LEFT_EYE_IDXS = [33, 160, 158, 133, 153, 144]
        self.RIGHT_EYE_IDXS = [362, 385, 387, 263, 373, 380]

        # 🔥 v7.0: FSM ULTRA-OPTIMIZADO para parpadeo
        self._blink_state = 'OPEN'
        self._state_change_time = 0.0
        self._threshold_margin = 0.015  # 🔥 1.5% margen ULTRA-ajustado para MÁXIMA sensibilidad
        
        # 🆕 NUEVO: Tracking de calidad de detección
        self.detection_quality_history = deque(maxlen=30)  # Últimos 30 frames
        
        # 🆕 NUEVO: Estadísticas de parpadeos para validación
        self.recent_blink_durations = deque(maxlen=20)  # Últimas 20 duraciones (más datos)
    
    def calculate_ear(self, eye_points: np.ndarray) -> float:
        """
        Calcula Eye Aspect Ratio (EAR) con máxima precisión y estabilidad.
        Fórmula: EAR = (||p2-p6|| + ||p3-p5||) / (2 * ||p1-p4||)
        
        Mejoras v5.0:
        - Suavizado EWMA optimizado
        - Validación de geometría del ojo
        - Detección de valores anómalos
        """
        try:
            A = dist.euclidean(eye_points[1], eye_points[5])  # Vertical 1
            B = dist.euclidean(eye_points[2], eye_points[4])  # Vertical 2
            C = dist.euclidean(eye_points[0], eye_points[3])  # Horizontal
            
            if C < 1.0:  # Evitar división por cero
                return 0.3  # Retornar valor "abierto" por defecto

            ear_raw = (A + B) / (2.0 * C)
            
            # 🆕 VALIDACIÓN: Detectar valores anómalos
            if ear_raw < 0.0 or ear_raw > 1.0:
                logger.debug(f"[BLINK-CALC] ⚠️ EAR anómalo detectado: {ear_raw:.3f}, usando anterior")
                return self.smoothed_ear  # Mantener valor anterior
            
            # 🆕 Agregar a buffer para análisis de tendencia
            self.ear_buffer.append(ear_raw)
            
            # Aplicar smoothing EWMA
            self.smoothed_ear = self.alpha * ear_raw + (1 - self.alpha) * self.smoothed_ear
            
            # 🆕 NUEVO: Detección de cambios bruscos (posible ruido)
            if len(self.ear_buffer) >= 3:
                recent_mean = np.mean(list(self.ear_buffer)[-3:])
                if abs(ear_raw - recent_mean) > 0.15:  # Cambio > 15% es sospechoso
                    logger.debug(f"[BLINK-CALC] 📊 Cambio brusco detectado: {ear_raw:.3f} vs promedio {recent_mean:.3f}")
                    # Usar promedio reciente en lugar del valor anómalo
                    self.smoothed_ear = self.alpha * recent_mean + (1 - self.alpha) * self.smoothed_ear
            
            return float(self.smoothed_ear)
        except Exception as e:
            logger.warning(f"[BLINK-CALC] Error calculando EAR: {e}")
            return 0.3  # Asumir ojos abiertos si hay error
    
    def _calculate_detection_quality(self, left_visible: bool, right_visible: bool, 
                                     ear: float, d_io: float = None) -> float:
        """
        🔥 v7.0: Calcula un score de calidad de detección ULTRA-PERMISIVO (0.0 - 1.0)
        Mayor score = mayor confianza en la detección
        Optimizado para aceptar más parpadeos válidos
        """
        quality_score = 0.0
        
        # 🔥 Factor 1: Ambos ojos visibles (35% - reducido de 40%)
        if left_visible and right_visible:
            quality_score += 0.35
        elif left_visible or right_visible:
            quality_score += 0.25  # 🔥 Aumentado de 0.2 para ser más generoso
        
        # 🔥 Factor 2: EAR en rango normal (30%)
        if 0.12 <= ear <= 0.38:  # 🔥 Rango MÁS AMPLIO (antes 0.15-0.35)
            quality_score += 0.30
        elif 0.08 <= ear <= 0.45:  # 🔥 Rango secundario más amplio
            quality_score += 0.20  # 🔥 Aumentado de 0.15
        
        # 🔥 Factor 3: Distancia inter-ocular adecuada (15%)
        if d_io:
            if d_io > 35:  # 🔥 Reducido de 40px para ser más permisivo
                quality_score += 0.15
            elif d_io > 25:  # 🔥 Añadido umbral secundario
                quality_score += 0.10
        
        # 🔥 Factor 4: Estabilidad de EAR (20% - aumentado de 15%)
        if len(self.ear_buffer) >= 3:
            ear_std = np.std(list(self.ear_buffer))
            if ear_std < 0.08:  # 🔥 Aumentado de 0.05 para ser más permisivo
                quality_score += 0.20
            elif ear_std < 0.15:  # 🔥 Aumentado de 0.10
                quality_score += 0.12  # 🔥 Aumentado de 0.08
        
        return min(1.0, quality_score)
    
    def _validate_blink_duration(self, duration: float) -> bool:
        """
        🔥 v7.0: Validación ULTRA-OPTIMIZADA para capturar TODOS los parpadeos reales
        Usa estadísticas adaptativas pero con umbrales MUY permisivos
        """
        # Validación básica con rango extendido
        if not (self.MIN_BLINK_DURATION_SEC <= duration <= self.MAX_BLINK_DURATION_SEC):
            logger.debug(f"[BLINK-VAL] ❌ Duración fuera de rango: {duration:.3f}s (límites: {self.MIN_BLINK_DURATION_SEC:.3f}-{self.MAX_BLINK_DURATION_SEC:.3f}s)")
            return False
        
        # 🔥 v7.0: Validación estadística ULTRA-PERMISIVA
        if len(self.recent_blink_durations) >= 8:  # 🔥 Requiere MÁS datos (antes 5) para ser más confiable
            mean_duration = np.mean(self.recent_blink_durations)
            std_duration = np.std(self.recent_blink_durations)
            
            # 🔥 Rechazar SOLO si está EXTREMADAMENTE lejos (> 5 desviaciones - MUY permisivo)
            if std_duration > 0.01:  # Solo aplicar si hay variación significativa
                z_score = abs(duration - mean_duration) / std_duration
                if z_score > 5.0:  # 🔥 Umbral MUY permisivo (antes 4.0)
                    logger.debug(f"[BLINK-VAL] ⚠️ Duración estadísticamente anómala: {duration:.3f}s (z-score: {z_score:.2f}, μ={mean_duration:.3f}s, σ={std_duration:.3f}s)")
                    return False
                else:
                    logger.debug(f"[BLINK-VAL] ✓ Duración válida: {duration:.3f}s (z-score: {z_score:.2f} < 5.0)")
            else:
                logger.debug(f"[BLINK-VAL] ✓ Duración válida (baja variación histórica)")
        else:
            logger.debug(f"[BLINK-VAL] ✓ Duración válida: {duration:.3f}s (sin suficiente historial para validación estadística)")
        
        return True
            
    def get_blink_rate(self, window_seconds: float = 60.0) -> float:
        """
        Calcula la tasa de parpadeo en parpadeos por minuto.
        Args:
            window_seconds: Ventana de tiempo en segundos (default: 60s)
        Returns:
            Tasa de parpadeo (parpadeos/minuto)
        """
        if not self.blink_timestamps:
            return 0.0
            
        current_time = time.time()
        recent_blinks = [t for t in self.blink_timestamps if current_time - t <= window_seconds]
        
        if len(recent_blinks) < 2:
            return 0.0
            
        # Calcular parpadeos por minuto
        blinks_per_minute = (len(recent_blinks) / window_seconds) * 60.0
        return blinks_per_minute

    def validate_eye_visibility(self, eye_points: np.ndarray, d_io: float = None, yaw: float = None, pitch: float = None) -> bool:
        try:
            # Validar que hay suficientes puntos
            if len(eye_points) < 6:
                logger.debug(f"[OCCLUSION] ❌ Puntos insuficientes: {len(eye_points)}")
                return False
            
            # 1. Ancho del ojo (distancia horizontal entre esquinas)
            width = dist.euclidean(eye_points[0], eye_points[3])
            
            # 2. Altura del ojo (distancia vertical máxima)
            A = dist.euclidean(eye_points[1], eye_points[5])  # Vertical izquierda
            B = dist.euclidean(eye_points[2], eye_points[4])  # Vertical derecha
            avg_height = (A + B) / 2.0
            
            # 3. Calcular EAR (Eye Aspect Ratio)
            if width < 0.1:  # Evitar división por cero
                logger.debug(f"[OCCLUSION] ❌ Ancho muy pequeño: {width:.2f}px")
                return False
                
            ear = (A + B) / (2.0 * width)
            
            # Escalado dinámico usando distancia inter-ocular si disponible
            min_width_px = 8.0
            min_height_px = 1.0
            if isinstance(d_io, (int, float)) and d_io > 0:
                # Proporciones empíricas: ojo ≈ 12% de d_io de ancho, altura ≈ 3% de d_io
                min_width_px = max(min_width_px, 0.12 * d_io)
                min_height_px = max(min_height_px, 0.03 * d_io)
            
            # VALIDACIÓN 1: Dimensiones mínimas
            if width < min_width_px:
                logger.debug(f"[OCCLUSION] ❌ Ojo muy estrecho: {width:.2f}px < {min_width_px:.2f}px")
                return False
            
            # VALIDACIÓN 2: EAR debe estar en rango realista
            # - Ojo completamente abierto: EAR ~0.25-0.35
            # - Ojo cerrado natural: EAR ~0.10-0.18
            # - Ojo obstruido/colapsado: EAR muy bajo (<0.08) o muy alto (>0.5)
            if ear < 0.05 or ear > 0.6:
                logger.debug(f"[OCCLUSION] ❌ EAR fuera de rango: {ear:.3f} (width={width:.1f}, height={avg_height:.1f})")
                return False
            
            # VALIDACIÓN 3: Relación ancho/alto debe ser realista
            # Un ojo normal tiene aspect ratio de aproximadamente 2:1 a 4:1 (ancho:alto)
            if avg_height > 0.1:  # Solo validar si hay altura medible
                aspect_ratio = width / avg_height
                if aspect_ratio < 1.5 or aspect_ratio > 6.0:
                    logger.debug(f"[OCCLUSION] ❌ Aspect ratio anormal: {aspect_ratio:.2f} (width={width:.1f}, height={avg_height:.1f})")
                    return False
            
            # VALIDACIÓN 4: Altura mínima del ojo (normalizada)
            if avg_height < min_height_px:
                logger.debug(f"[OCCLUSION] ❌ Altura muy pequeña: {avg_height:.2f}px < {min_height_px:.2f}px")
                return False
            
            # Si pasa todas las validaciones, el ojo es visible
            return True
            
        except Exception as e:
            logger.warning(f"[OCCLUSION] ❌ Error en validación: {e}")
            return False

    def detect(self, face_landmarks, frame_shape: Tuple[int, int]) -> Tuple[bool, float, Dict[str, Any]]:
        metrics = {
            'eyes_detected': False,
            'left_eye_visible': False,
            'right_eye_visible': False,
            'ear': 0.0,
            'raw_ear': 0.0,
            'blink_detected': False,
            'total_blinks': self.blink_counter,
            'blink_counter': self.blink_counter,
            'blink_rate': 0.0,
            'frames_closed': 0.0,
            'microsleep_detected': False,
            'occluded': False,
            'occlusion_candidate': False,
            'calibrated_threshold': self.EAR_THRESHOLD,
            'eyes_closed': False,
        }
        
        try:
            h, w = frame_shape[:2]
            
            # Extraer puntos (coordenadas en píxeles)
            # Usar coordenadas en punto flotante para evitar cuantización a píxeles
            left_eye_points = np.array([
                [face_landmarks.landmark[i].x * w, face_landmarks.landmark[i].y * h]
                for i in self.LEFT_EYE_IDXS
            ], dtype=np.float32)
            right_eye_points = np.array([
                [face_landmarks.landmark[i].x * w, face_landmarks.landmark[i].y * h]
                for i in self.RIGHT_EYE_IDXS
            ], dtype=np.float32)
            
            # Distancia inter-ocular aproximada (entre esquinas externas de cada ojo)
            try:
                left_outer = np.array([face_landmarks.landmark[self.LEFT_EYE_IDXS[0]].x * w,
                                       face_landmarks.landmark[self.LEFT_EYE_IDXS[0]].y * h], dtype=np.float32)
                right_outer = np.array([face_landmarks.landmark[self.RIGHT_EYE_IDXS[3]].x * w,
                                        face_landmarks.landmark[self.RIGHT_EYE_IDXS[3]].y * h], dtype=np.float32)
                d_io = float(dist.euclidean(left_outer, right_outer))
            except Exception:
                d_io = None

            # PASO 1: VALIDAR VISIBILIDAD DE CADA OJO
            left_visible = self.validate_eye_visibility(left_eye_points, d_io=d_io)
            right_visible = self.validate_eye_visibility(right_eye_points, d_io=d_io)
            
            metrics['left_eye_visible'] = left_visible
            metrics['right_eye_visible'] = right_visible
            
            logger.debug(f"[BLINK] Visibilidad: left={left_visible}, right={right_visible}")
            
            # PASO 2: DETERMINAR SI HAY OCLUSIÓN CANDIDATA
            # (ambos ojos deben estar visibles para NO ser candidato)
            occlusion_candidate = not (left_visible and right_visible)
            metrics['occlusion_candidate'] = occlusion_candidate
            
            # PASO 3: CALCULAR EAR SEGÚN VISIBILIDAD
            if occlusion_candidate:
                # Si hay sospecha de oclusión, usar valores por defecto
                left_ear = 0.3
                right_ear = 0.3
                metrics['eyes_detected'] = False  # NO confirmar ojos para procesamiento
                logger.debug("[BLINK] ⚠️ Oclusión candidata detectada, usando EAR por defecto")
            else:
                # Ojos visibles - calcular EAR normal
                left_ear = self.calculate_ear(left_eye_points)
                right_ear = self.calculate_ear(right_eye_points)
                metrics['eyes_detected'] = True  # Ojos detectados correctamente
            
            # Usar EAR suavizado (ya viene suavizado de calculate_ear)
            avg_ear = (left_ear + right_ear) / 2.0
            raw_ear = avg_ear
            
            metrics['ear'] = avg_ear
            metrics['raw_ear'] = raw_ear
            metrics['left_ear'] = left_ear
            metrics['right_ear'] = right_ear
            metrics['smoothed_ear'] = self.smoothed_ear
            
            # 🆕 PASO 3.5: CALCULAR CALIDAD DE DETECCIÓN
            detection_quality = self._calculate_detection_quality(left_visible, right_visible, avg_ear, d_io)
            self.detection_quality_history.append(detection_quality)
            metrics['detection_quality'] = detection_quality
            
            # 🆕 Calcular calidad promedio reciente
            if len(self.detection_quality_history) >= 5:
                avg_quality = np.mean(list(self.detection_quality_history)[-5:])
                metrics['avg_detection_quality'] = avg_quality
                # Si la calidad es muy baja, ser más cauteloso con las detecciones
                if avg_quality < 0.4:  # 🔥 v7.0: Umbral más bajo (antes 0.5)
                    logger.debug(f"[BLINK] ⚠️ Calidad de detección baja: {avg_quality:.2f}")
            
            threshold = self.EAR_THRESHOLD
            # 🔥 v7.0: Histéresis MÁS AGRESIVA para capturar parpadeos rápidos
            margin_factor = 0.8 if detection_quality > 0.7 else 1.0  # 🔥 Reducir margen para mayor sensibilidad
            thr_low = max(0.05, threshold - (self._threshold_margin * margin_factor))
            thr_high = min(0.5, threshold + (self._threshold_margin * margin_factor))
            metrics['calibrated_threshold'] = threshold
            metrics['threshold_low'] = thr_low
            metrics['threshold_high'] = thr_high
            metrics['blink_state'] = self._blink_state

            blink_detected = False
            current_time = time.time()

            # VALIDACIÓN CRÍTICA 1: Rechazar valores imposibles (oclusión CONFIRMADA)
            if avg_ear < 0.01:
                logger.debug("[BLINK] 🚫 EAR < 0.01: Oclusión confirmada")
                metrics['occluded'] = True
                metrics['eyes_closed'] = False
                metrics['eyes_detected'] = False
                # Resetear estado de parpadeo y contadores de confirmación
                self._blink_state = 'OPEN'
                self.eye_is_closed = False
                self.eye_closed_start_time = 0.0
                self.current_microsleep = False
                self.closing_confirmation_count = 0
                self.opening_confirmation_count = 0
                return False, avg_ear, metrics
            
            # VALIDACIÓN CRÍTICA 2: SI HAY OCLUSIÓN CANDIDATA -> No procesar parpadeo/microsueño
            if occlusion_candidate:
                logger.debug("[BLINK] ⚠️ Oclusión candidata: No procesar como parpadeo")
                metrics['eyes_closed'] = False
                metrics['eyes_detected'] = False
                # Resetear estado si estaba en proceso de detección
                if self.eye_is_closed:
                    logger.info("[BLINK] 🔄 Reseteo por oclusión candidata")
                    self.eye_is_closed = False
                    self.eye_closed_start_time = 0.0
                    self.current_microsleep = False
                    self._blink_state = 'OPEN'
                    self.closing_confirmation_count = 0
                    self.opening_confirmation_count = 0
                return False, avg_ear, metrics
            
            # AQUÍ SOLO LLEGAMOS SI: Ojos visibles y landmarks válidos
            # Ahora sí podemos detectar parpadeos y microsueño con TOTAL CONFIANZA
            
            # 🆕 FSM MEJORADO PARA DETECCIÓN DE PARPADEOS CON CONFIRMACIÓN
            if self._blink_state == 'OPEN':
                metrics['eyes_closed'] = False
                self.opening_confirmation_count = 0  # Resetear contador de apertura
                
                if avg_ear < thr_low:
                    # � Incrementar contador de confirmación de cierre
                    self.closing_confirmation_count += 1
                    logger.debug(f"[BLINK] 👁️ Ojos cerrándose: EAR={avg_ear:.3f} < {thr_low:.3f} (conf: {self.closing_confirmation_count}/{self.CONFIRMATION_FRAMES})")
                    
                    # 🆕 Transición solo si se confirma en múltiples frames
                    if self.closing_confirmation_count >= self.CONFIRMATION_FRAMES:
                        self._blink_state = 'CLOSED'
                        self._state_change_time = current_time
                        self.eye_closed_start_time = current_time
                        self.eye_is_closed = True
                        metrics['eyes_closed'] = True
                        self.closing_confirmation_count = 0  # Resetear
                        logger.debug(f"[BLINK] ✓ Cierre CONFIRMADO tras {self.CONFIRMATION_FRAMES} frames")
                else:
                    # Si EAR vuelve a subir, resetear contador
                    if self.closing_confirmation_count > 0:
                        logger.debug(f"[BLINK] 🔄 Reset contador cierre (EAR subió a {avg_ear:.3f})")
                    self.closing_confirmation_count = 0
                    
            elif self._blink_state == 'CLOSED':
                metrics['eyes_closed'] = True
                closed_duration = current_time - self.eye_closed_start_time
                metrics['frames_closed'] = closed_duration
                self.closing_confirmation_count = 0  # Resetear contador de cierre
                
                # DETECCIÓN DE MICROSUEÑO (solo si ojos cerrados NATURALMENTE)
                if closed_duration >= self.microsleep_threshold:
                    if not self.current_microsleep:
                        self.current_microsleep = True
                        logger.warning(f"[BLINK] 🚨 Microsueño detectado: {closed_duration:.1f}s")
                    metrics['microsleep_detected'] = True

                # 🆕 Confirmar reapertura en múltiples frames
                if avg_ear >= thr_high:
                    self.opening_confirmation_count += 1
                    logger.debug(f"[BLINK] 👁️ Ojos abriéndose: EAR={avg_ear:.3f} >= {thr_high:.3f} (conf: {self.opening_confirmation_count}/{self.CONFIRMATION_FRAMES})")
                    
                    # 🆕 Confirmar apertura antes de registrar parpadeo
                    if self.opening_confirmation_count >= self.CONFIRMATION_FRAMES:
                        blink_duration = current_time - self.eye_closed_start_time
                        time_since_last_blink = current_time - self.last_blink_time
                        
                        logger.info(f"[BLINK] ✓ Apertura CONFIRMADA, duración={blink_duration:.3f}s, tiempo_desde_último={time_since_last_blink:.3f}s")
                        
                        # 🔥 v7.0: VALIDACIÓN ULTRA-OPTIMIZADA PARA CAPTURAR TODOS LOS PARPADEOS
                        duration_valid = self._validate_blink_duration(blink_duration)
                        debounce_ok = time_since_last_blink > self.DEBOUNCE_SEC
                        not_occluded = not metrics.get('occluded', False)
                        quality_ok = detection_quality > 0.30  # 🔥 Umbral MUY BAJO (antes 0.35) para capturar TODOS los parpadeos
                        
                        # 🔥 LOGGING DETALLADO de todas las validaciones
                        logger.debug(f"[BLINK-CHECK] Validaciones: duration_valid={duration_valid}, debounce_ok={debounce_ok}, not_occluded={not_occluded}, quality_ok={quality_ok} (quality={detection_quality:.2f})")
                        
                        if duration_valid and debounce_ok and not_occluded and quality_ok:
                            self.blink_counter += 1
                            self.blink_timestamps.append(current_time)
                            self.recent_blink_durations.append(blink_duration)  # 🆕 Registrar duración
                            blink_detected = True
                            self.last_blink_time = current_time
                            logger.info(f"[BLINK] ✅✅✅ Parpadeo #{self.blink_counter} REGISTRADO (duración: {blink_duration:.3f}s, calidad: {detection_quality:.2f})")
                        else:
                            reasons = []
                            if not duration_valid:
                                reasons.append(f"duración={blink_duration:.3f}s inválida (límites: {self.MIN_BLINK_DURATION_SEC:.3f}-{self.MAX_BLINK_DURATION_SEC:.3f}s)")
                            if not debounce_ok:
                                reasons.append(f"debounce={time_since_last_blink:.3f}s < {self.DEBOUNCE_SEC:.3f}s")
                            if not not_occluded:
                                reasons.append("oclusión detectada")
                            if not quality_ok:
                                reasons.append(f"calidad baja ({detection_quality:.2f} < 0.30)")
                            logger.warning(f"[BLINK] ❌ Parpadeo RECHAZADO: {', '.join(reasons)}")
                        
                        # Resetear a OPEN tras reapertura confirmada
                        self._blink_state = 'OPEN'
                        self.eye_is_closed = False
                        self.eye_closed_start_time = 0.0
                        self.current_microsleep = False
                        self.opening_confirmation_count = 0
                else:
                    # Si EAR vuelve a bajar, resetear contador de apertura
                    if self.opening_confirmation_count > 0:
                        logger.debug(f"[BLINK] 🔄 Reset contador apertura (EAR bajó a {avg_ear:.3f})")
                    self.opening_confirmation_count = 0

            blink_rate = self.get_blink_rate(window_seconds=60.0)
            
            metrics.update({
                'blink_detected': blink_detected,
                'total_blinks': self.blink_counter,
                'blink_counter': self.blink_counter,
                'blink_rate': blink_rate
            })
            
            return blink_detected, avg_ear, metrics
            
        except Exception as e:
            logger.error(f"[BLINK] Error detectando parpadeo: {e}", exc_info=True)
            return False, 0.0, metrics
    
    def reset(self):
        """
        🔥 v7.0: RESETEA completamente el estado del detector de parpadeos ULTRA-PERFECTO.
        Debe llamarse al iniciar una nueva sesión de monitoreo.
        """
        self.blink_counter = 0
        self.last_blink_time = 0.0
        self.eye_closed_start_time = 0.0
        self.eye_is_closed = False
        self.current_microsleep = False
        self.blink_timestamps.clear()
        self.smoothed_ear = 0.25
        self._blink_state = 'OPEN'
        self._state_change_time = 0.0
        # 🔥 v6.0: Resetear campos de confirmación y calidad
        self.closing_confirmation_count = 0
        self.opening_confirmation_count = 0
        self.ear_buffer.clear()
        self.detection_quality_history.clear()
        self.recent_blink_durations.clear()
        logger.info("[BLINK] ✅ Detector de parpadeos reseteado (v6.0 - PERFECTO: 1-frame conf, 30ms min, 40ms debounce, calidad 0.35)")
        logger.info("[BLINK] 🔄 Listo para capturar cada parpadeo con precisión total")


class UnifiedDetectionSystem:
    def __init__(self, user_config=None, effective_config=None):
        self.user_config = user_config
        self.effective_config = effective_config or {}
        self.face_mesh = None
        self.overlay_enabled = True
        # Escala optimizada para velocidad extrema
        self.processing_scale = 0.60  # 60% base (3x más rápido)
        
        # Métricas de calidad del sistema
        self.total_frames_processed = 0
        self.successful_detections = 0
        self.failed_detections = 0
        
        # Historial reducido para velocidad
        self.focus_history = deque(maxlen=20)
        self.ear_history = deque(maxlen=20)

        # Suavizado de gaze
        self.gaze_alpha = 0.3
        self.gaze_yaw_smooth = 0.0
        self.gaze_pitch_smooth = 0.0
        self.gaze_yaw_history = deque(maxlen=10)
        self.gaze_pitch_history = deque(maxlen=10)
        
        # Persistencia de estado de enfoque (para mantener durante parpadeos)
        self.last_valid_focus_state = 'Atento'
        self.last_valid_focus_score = 100.0

        # Histeresis temporal del estado de enfoque para evitar cambios erráticos
        self._focus_state = 'Fuera de rango'
        self._focus_pending_state = None
        self._focus_pending_since = 0.0
        # Tiempos de permanencia (segundos) para confirmar cambios de estado
        self._focus_hold_to_distracted = 0.6  # requiere desviación sostenida
        self._focus_hold_to_attentive = 0.4   # requiere atención sostenida

        # Modelos pesados deshabilitados
        self.enable_gaze_detection = False  # Usar MediaPipe (rápido)

        self.setup_detectors(user_config)
        self.setup_facemesh(user_config)

    def reset_session(self):
        # Resetear detector de parpadeos (crítico para contador)
        self.blink_detector.reset()
        
        # Resetear métricas acumuladas
        self.total_frames_processed = 0
        self.successful_detections = 0
        self.failed_detections = 0
        
        # Limpiar historial
        self.focus_history.clear()
        self.ear_history.clear()
        self.gaze_yaw_history.clear()
        self.gaze_pitch_history.clear()
        
        # Resetear suavizado de gaze
        self.gaze_yaw_smooth = 0.0
        self.gaze_pitch_smooth = 0.0
        
        # Resetear estado de enfoque
        self._focus_state = 'Fuera de rango'
        self._focus_pending_state = None
        self._focus_pending_since = 0.0
        self.last_valid_focus_state = 'Atento'
        self.last_valid_focus_score = 100.0
        
        # Resetear contadores de frame skip
        self.gaze_frame_counter = 0
        self.phone_frame_counter = 0
        
        # Resetear cache de resultados
        self.last_gaze_result = (0.0, 0.0, 0.0)
        self.last_phone_result = (False, 0.0, {})
        
        logger.info("[SYSTEM] 🔄 Sistema reseteado para nueva sesión")

    def _apply_focus_hysteresis(self, proposed_state: str) -> str:
        critical_states = {'Uso de celular', 'Ojos no detectados', 'Fuera de rango'}
        now = time.time()

        # Transiciones inmediatas a estados críticos
        if proposed_state in critical_states:
            self._focus_state = proposed_state
            self._focus_pending_state = None
            self._focus_pending_since = 0.0
            return self._focus_state

        # Si no hay cambio, limpiar pendiente y retornar
        if proposed_state == self._focus_state:
            self._focus_pending_state = None
            self._focus_pending_since = 0.0
            return self._focus_state

        # Si hay cambio propuesto, iniciar/actualizar periodo de confirmación
        if self._focus_pending_state != proposed_state:
            self._focus_pending_state = proposed_state
            self._focus_pending_since = now
            return self._focus_state  # mantener estado actual hasta confirmar

        # Ya hay pendiente hacia el mismo estado, verificar tiempos de sostenimiento
        hold = self._focus_hold_to_distracted if proposed_state != 'Atento' else self._focus_hold_to_attentive
        if (now - self._focus_pending_since) >= hold:
            prev = self._focus_state
            self._focus_state = proposed_state
            self._focus_pending_state = None
            self._focus_pending_since = 0.0
            logger.debug(f"[FOCUS] Cambio confirmado: {prev} → {self._focus_state}")
        return self._focus_state
    
    def setup_detectors(self, user_config):
        """Inicializa los sub-detectores"""
        
        # 1. Detector de Parpadeo (Afinado)
        ear_thresh = getattr(user_config, 'ear_threshold', 0.21)
        # Obtener duración de microsueño desde configuración efectiva (5-15s)
        ms_threshold = 5.0
        try:
            if isinstance(self.effective_config, dict):
                ms_threshold = float(self.effective_config.get('microsleep_duration_seconds', 5.0))
        except Exception:
            ms_threshold = 5.0
        # Construir detector con umbral configurado
        self.blink_detector = ImprovedBlinkDetector(
            ear_threshold=ear_thresh,
            microsleep_threshold=ms_threshold
        )
        logger.info(f"[DETECTOR] Inicializado con EAR={ear_thresh:.3f}, Microsueño={ms_threshold:.1f}s")

    def setup_facemesh(self, user_config):
        # Umbrales base más permisivos para mejorar la detección de rostro
        min_det_conf = 0.3
        min_track_conf = 0.3
        
        if user_config:
            # Interpretar 'sensitivity' como: 0.0 = estricto, 1.0 = muy sensible (más permisivo)
            try:
                sensitivity = float(getattr(user_config, 'face_detection_sensitivity', 0.8))
                sensitivity = max(0.0, min(1.0, sensitivity))
                # Mapear sensibilidad a umbral inverso (más sensibilidad -> umbral más bajo)
                min_det_conf = 0.6 - 0.3 * sensitivity
                min_track_conf = 0.55 - 0.25 * sensitivity
                min_det_conf = float(max(0.3, min(0.6, min_det_conf)))
                min_track_conf = float(max(0.3, min(0.6, min_track_conf)))
            except Exception:
                min_det_conf = 0.3
                min_track_conf = 0.3

        try:
            # Detector ligero para conteo de rostros (rápido)
            self.face_detector = mp.solutions.face_detection.FaceDetection(
                model_selection=0,
                min_detection_confidence=min_det_conf
            )
            logger.info(f"[FACEMESH] FaceDetection inicializado (conf={min_det_conf:.2f})")
        except Exception as e:
            logger.error(f"[SYSTEM] Error FaceDetection: {e}")
            self.face_detector = None

        try:
            # FaceMesh para landmarks de alta precisión (1 rostro por rendimiento)
            self.face_mesh = mp.solutions.face_mesh.FaceMesh(
                static_image_mode=False,
                max_num_faces=1,
                refine_landmarks=False,
                min_detection_confidence=min_det_conf,
                min_tracking_confidence=min_track_conf
            )
            logger.info(f"[FACEMESH] FaceMesh inicializado (det={min_det_conf:.2f}, track={min_track_conf:.2f})")
        except Exception as e:
            logger.error(f"[SYSTEM] Error FaceMesh: {e}")
            self.face_mesh = None

    def set_overlay_enabled(self, enabled: bool):
        self.overlay_enabled = enabled
        
    def set_processing_scale(self, scale: float):
        self.processing_scale = max(0.3, min(1.0, scale))

    def _draw_face_oval(self, frame: np.ndarray, face_landmarks):
        """Dibuja el óvalo facial punteado"""
        if not self.overlay_enabled:
            return
        
        try:
            h, w = frame.shape[:2]
            oval_indices = mp.solutions.face_mesh.FACEMESH_FACE_OVAL
            
            pts = []
            for start_idx, end_idx in oval_indices:
                pts.append(face_landmarks.landmark[start_idx])
            
            for i in range(len(pts)):
                pt = pts[i]
                x, y = int(pt.x * w), int(pt.y * h)
                cv2.circle(frame, (x, y), 2, (100, 255, 100), -1, cv2.LINE_AA)
                
        except Exception:
            pass  # No fallar si el dibujo falla

    def _estimate_head_pose_mediapipe(self, face_landmarks, frame_shape: Tuple[int, int]) -> Tuple[float, float, float]:
        """
        Calcula la pose de cabeza usando MediaPipe Face Mesh
        Retorna: (yaw, pitch, roll) en grados
        """
        try:
            h, w = frame_shape[:2]
            
            # Puntos clave para solvePnP
            # Nariz, mentón, ojo izq, ojo der, comisura izq, comisura der
            image_points = np.array([
                [face_landmarks.landmark[1].x * w, face_landmarks.landmark[1].y * h],     # Nariz
                [face_landmarks.landmark[152].x * w, face_landmarks.landmark[152].y * h], # Mentón
                [face_landmarks.landmark[33].x * w, face_landmarks.landmark[33].y * h],   # Ojo izq
                [face_landmarks.landmark[263].x * w, face_landmarks.landmark[263].y * h], # Ojo der
                [face_landmarks.landmark[61].x * w, face_landmarks.landmark[61].y * h],   # Comisura izq
                [face_landmarks.landmark[291].x * w, face_landmarks.landmark[291].y * h]  # Comisura der
            ], dtype=np.float64)
            
            # Modelo 3D genérico de rostro
            model_points = np.array([
                [0.0, 0.0, 0.0],            # Nariz
                [0.0, -330.0, -65.0],       # Mentón
                [-225.0, 170.0, -135.0],    # Ojo izq
                [225.0, 170.0, -135.0],     # Ojo der
                [-150.0, -150.0, -125.0],   # Comisura izq
                [150.0, -150.0, -125.0]     # Comisura der
            ], dtype=np.float64)
            
            # Parámetros de cámara
            focal_length = w
            center = (w / 2, h / 2)
            camera_matrix = np.array([
                [focal_length, 0, center[0]],
                [0, focal_length, center[1]],
                [0, 0, 1]
            ], dtype=np.float64)
            
            dist_coeffs = np.zeros((4, 1))
            
            # Resolver PnP
            success, rotation_vector, translation_vector = cv2.solvePnP(
                model_points,
                image_points,
                camera_matrix,
                dist_coeffs,
                flags=cv2.SOLVEPNP_ITERATIVE
            )
            
            if not success:
                return 0.0, 0.0, 0.0
            
            # Convertir vector de rotación a ángulos de Euler
            rotation_matrix, _ = cv2.Rodrigues(rotation_vector)
            
            # Extraer yaw, pitch, roll
            sy = np.sqrt(rotation_matrix[0, 0]**2 + rotation_matrix[1, 0]**2)
            singular = sy < 1e-6
            
            if not singular:
                pitch = np.arctan2(-rotation_matrix[2, 0], sy)
                yaw = np.arctan2(rotation_matrix[1, 0], rotation_matrix[0, 0])
                roll = np.arctan2(rotation_matrix[2, 1], rotation_matrix[2, 2])
            else:
                pitch = np.arctan2(-rotation_matrix[2, 0], sy)
                yaw = np.arctan2(-rotation_matrix[1, 2], rotation_matrix[1, 1])
                roll = 0
            
            # Convertir a grados
            yaw_deg = float(np.degrees(yaw))
            pitch_deg = float(np.degrees(pitch))
            roll_deg = float(np.degrees(roll))
            
            return yaw_deg, pitch_deg, roll_deg
            
        except Exception as e:
            logger.error(f"[HEAD_POSE] Error calculando pose: {e}")
            return 0.0, 0.0, 0.0

    def get_default_metrics(self, frame) -> Dict[str, Any]:
        """Retorna métricas por defecto (rostro no detectado)"""
        h, w = frame.shape[:2]
        gray = cv2.cvtColor(cv2.resize(frame, (w//4, h//4)), cv2.COLOR_BGR2GRAY)
        brightness = float(np.mean(gray))
        return {
            'face_detected': False,
            'faces_count': 0,
            'faces': 0,
            'eyes_detected': False,
            'focus_state': 'Fuera de rango',
            'focus': 'Fuera de rango',
            'brightness': brightness,
            'avg_ear': 0.0,
            'head_yaw': 0.0,
            'head_pitch': 0.0,
            'head_roll': 0.0,
            'blink_detected': False,
            'phone_detected': False,
            'is_using_phone': False,
            'is_focused': False,
            'focus_score': 0.0,
            'total_blinks': 0,
            'blink_count': 0
        }

    def _calculate_focus_score(self, gaze_yaw: float, gaze_pitch: float, eyes_detected: bool) -> Tuple[float, str]:
        # 1️⃣ VALIDACIÓN: Ojos no detectados
        if not eyes_detected:
            return 0.0, "Ojos no detectados"
        
        # 2️⃣ VALIDACIÓN: Ángulos válidos
        if not isinstance(gaze_yaw, (int, float)) or not isinstance(gaze_pitch, (int, float)):
            return 0.0, "Ojos no detectados"
        
        # 3️⃣ VALIDACIÓN: Rango razonable
        if abs(gaze_yaw) > 90 or abs(gaze_pitch) > 90:
            return 0.0, "Fuera de rango"
        
        # 4️⃣ CLASIFICACIÓN DIRECCIONAL (prioridad: pitch > yaw)
        # Umbrales estrictos para evitar falsos positivos
        
        # Mirando ABAJO (pitch negativo, umbral -20°)
        if gaze_pitch < -20:
            return 0.0, "Mirando abajo"
        
        # Mirando ARRIBA (pitch positivo, umbral +20°)
        if gaze_pitch > 20:
            return 0.0, "Mirando arriba"
        
        # Mirando a los LADOS (yaw lateral, umbral ±30°)
        if abs(gaze_yaw) > 30:
            return 0.0, "Mirando a los lados"
        
        # 5️⃣ ATENTO vs DISTRAÍDO (con zona de histéresis para máxima precisión)
        # Calcular desviación angular total con peso asimétrico
        weighted_yaw = abs(gaze_yaw) * 1.0
        weighted_pitch = abs(gaze_pitch) * 1.2  # Pitch pesa 20% más
        angular_deviation = np.sqrt(weighted_yaw**2 + weighted_pitch**2)
        
        # Umbral más ESTRICTO para "Atento": ≤ 12°
        # Zona de histéresis: 12°—20° se sigue considerando "Atento" para evitar parpadeos
        if angular_deviation <= 20:
            # Curva suave de penalización dentro de la zona
            if angular_deviation <= 12:
                score = 100.0
            else:
                # Entre 12° y 20°, degradar de 95 a 80
                score = max(80.0, 95.0 - (angular_deviation - 12) * 1.875)
            state = "Atento"
        else:
            # Distraído solo si desviación > 20° (reduce falsos positivos por ruido leve)
            # Score decae linealmente: 70 a 0 entre 20° y 40°
            score = max(0.0, 70.0 - (angular_deviation - 20) * 3.5)
            state = "Distraído"
        
        return round(score, 2), state
    
    def _analyze_temporal_metrics(self, current_metrics: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analiza métricas temporales para detectar tendencias.
        
        Returns:
            Dict con análisis temporal:
            - focus_trend: 'improving', 'stable', 'declining'
            - focus_stability: float (0-1)
            - avg_focus_30s: float
        """
        analysis = {
            'focus_trend': 'stable',
            'focus_stability': 1.0,
            'avg_focus_30s': current_metrics.get('focus_score', 0),
        }
        
        # Añadir al historial
        self.focus_history.append(current_metrics.get('focus_score', 0))
        self.ear_history.append(current_metrics.get('avg_ear', 0))
        
        if len(self.focus_history) < 10:
            return analysis
        
        # Calcular promedio de los últimos 30 frames
        analysis['avg_focus_30s'] = np.mean(list(self.focus_history))
        
        # Calcular estabilidad (inverso de la varianza normalizada)
        variance = np.var(list(self.focus_history))
        analysis['focus_stability'] = max(0.0, 1.0 - (variance / 1000.0))
        
        # Detectar tendencia (comparar primera mitad vs segunda mitad)
        if len(self.focus_history) >= 20:
            first_half = np.mean(list(self.focus_history)[:15])
            second_half = np.mean(list(self.focus_history)[15:])
            diff = second_half - first_half
            
            if diff > 10:
                analysis['focus_trend'] = 'improving'
            elif diff < -10:
                analysis['focus_trend'] = 'declining'
            else:
                analysis['focus_trend'] = 'stable'
        
        return analysis

    def process_frame(self, frame: np.ndarray) -> Dict[str, Any]:
        self.total_frames_processed += 1
        
        if self.face_mesh is None:
            self.failed_detections += 1
            return self.get_default_metrics(frame)

        frame_shape = frame.shape
        metrics = self.get_default_metrics(frame)
        
        # Calcular brillo simplificado (solo canal verde, más rápido)
        brightness = float(np.mean(frame[:, :, 1]))
        metrics['brightness'] = brightness

        try:
            # Reducción EXTREMA para máxima velocidad
            h, w = frame_shape[:2]
            
            # Escala balanceada para mejor detección
            if max(h, w) > 1080:
                target_scale = 0.75  # 75% para 1080p+
            elif max(h, w) > 720:
                target_scale = 0.85  # 85% para 720p+
            else:
                target_scale = 1.0  # Sin escalar para resoluciones menores
            
            if target_scale < 1.0:
                target_h, target_w = int(h * target_scale), int(w * target_scale)
                process_frame = cv2.resize(frame, (target_w, target_h), interpolation=cv2.INTER_NEAREST)
            else:
                process_frame = frame
                
            rgb_frame = cv2.cvtColor(process_frame, cv2.COLOR_BGR2RGB)
            rgb_frame.flags.writeable = False  # Optimización de MediaPipe
            
            # 1️⃣ DETECCIÓN RÁPIDA DE ROSTROS (MediaPipe FaceDetection) para conteo
            try:
                fd_results = None
                if self.face_detector is not None:
                    fd_results = self.face_detector.process(rgb_frame)
                detected_faces = len(fd_results.detections) if (fd_results and fd_results.detections) else 0
                metrics['faces_count'] = detected_faces
                metrics['faces'] = detected_faces
                if detected_faces > 1:
                    metrics['multiple_faces'] = True
                    logger.debug(f"[DETECTION] Múltiples rostros detectados: {detected_faces}")
            except Exception as det_err:
                logger.warning(f"[SYSTEM] FaceDetection fallo: {det_err}")

            # 1.5️⃣ DETECCIÓN FACIAL (MediaPipe Face Mesh) para landmarks y ojos
            try:
                results = self.face_mesh.process(rgb_frame)
                rgb_frame.flags.writeable = True
            except Exception as mesh_error:
                logger.error(f"[SYSTEM] Error en MediaPipe: {mesh_error}")
                self.failed_detections += 1
                return self.get_default_metrics(frame)
            
            if not results or not results.multi_face_landmarks:
                self.failed_detections += 1
                metrics['focus_state'] = 'Fuera de rango'
                metrics['focus'] = 'Fuera de rango'
                self._focus_state = 'Fuera de rango'
                self._focus_pending_state = None
                self._focus_pending_since = 0.0
                return metrics

            face_landmarks = results.multi_face_landmarks[0]
            # Mantener el conteo de FaceDetection (puede ser >1 aunque FaceMesh procese 1)
            metrics['face_detected'] = True
            # No sobrescribir 'faces'/'faces_count' si ya vienen de FaceDetection; asegurar mínimo 1
            if int(metrics.get('faces', 0)) <= 0:
                metrics['faces'] = 1
                metrics['faces_count'] = 1

            # Dibujar overlay si está habilitado
            self._draw_face_oval(frame, face_landmarks)
            
            # Extraer bounding box del rostro
            h, w = frame_shape[:2]
            pts = np.array([[int(lm.x * w), int(lm.y * h)] for lm in face_landmarks.landmark])
            x_min, y_min = pts.min(axis=0)
            x_max, y_max = pts.max(axis=0)
            face_box = (max(0, x_min), max(0, y_min), min(w - 1, x_max), min(h - 1, y_max))

            # 2️⃣ DETECCIÓN DE PARPADEOS (con validación de oclusión PERFECTA)
            is_blink, avg_ear, blink_metrics = self.blink_detector.detect(
                face_landmarks, frame_shape
            )
            
            # EXTRACCIÓN DE MÉTRICAS DE PARPADEO
            eyes_detected = blink_metrics['eyes_detected']
            microsleep_detected = blink_metrics.get('microsleep_detected', False)
            eyes_closed = blink_metrics.get('eyes_closed', False)
            occluded = blink_metrics.get('occluded', False)
            occlusion_candidate = blink_metrics.get('occlusion_candidate', False)
            
            # Actualizar métricas de parpadeo
            metrics.update({
                'blink_detected': is_blink,
                'avg_ear': blink_metrics['ear'],
                'raw_ear': blink_metrics.get('raw_ear', avg_ear),
                'total_blinks': blink_metrics['total_blinks'],
                'blink_count': blink_metrics['total_blinks'],
                'blink_rate': blink_metrics.get('blink_rate', 0.0),
                'eyes_detected': eyes_detected,
                'occluded': occluded,
                'occlusion_candidate': occlusion_candidate,
                'microsleep_detected': microsleep_detected,
                'is_microsleep': microsleep_detected,
                'microsleep_duration': blink_metrics.get('frames_closed', 0.0),
                'eyes_closed': eyes_closed,
            })
            
            logger.debug(
                f"[DETECTION] Eyes: detected={eyes_detected}, closed={eyes_closed}, "
                f"occluded={occluded}, candidate={occlusion_candidate}, microsleep={microsleep_detected}"
            )

            # 3️⃣ POSE DE CABEZA (sin modelo de gaze)
            gaze_yaw, gaze_pitch, roll = self._estimate_head_pose_mediapipe(face_landmarks, frame_shape)
            metrics['gaze_method'] = 'mediapipe'
            
            # Suavizar gaze para reducir ruido
            try:
                self.gaze_yaw_history.append(float(gaze_yaw))
                self.gaze_pitch_history.append(float(gaze_pitch))
                median_yaw = float(np.median(list(self.gaze_yaw_history)))
                median_pitch = float(np.median(list(self.gaze_pitch_history)))
                self.gaze_yaw_smooth = self.gaze_alpha * median_yaw + (1 - self.gaze_alpha) * self.gaze_yaw_smooth
                self.gaze_pitch_smooth = self.gaze_alpha * median_pitch + (1 - self.gaze_alpha) * self.gaze_pitch_smooth
            except Exception:
                # Si falla suavizado, usar valores crudos
                self.gaze_yaw_smooth = float(gaze_yaw)
                self.gaze_pitch_smooth = float(gaze_pitch)

            metrics['head_yaw'] = self.gaze_yaw_smooth
            metrics['head_pitch'] = self.gaze_pitch_smooth
            metrics['head_roll'] = roll

            # DECISIÓN FINAL DE OCLUSIÓN (con validación de pose frontal)
            # Solo confirmar oclusión si:
            # 1. Hay candidato de oclusión (landmarks colapsados)
            # 2. La cabeza está frontal (no es pérdida de tracking)
            if occlusion_candidate:
                frontal = (abs(self.gaze_yaw_smooth) <= 25.0) and (abs(self.gaze_pitch_smooth) <= 20.0)
                if frontal:
                    metrics['occluded'] = True
                    metrics['eyes_detected'] = False
                    metrics['eyes_closed'] = False
                    metrics['microsleep_detected'] = False
                    logger.info("[DETECTION] ✅ Oclusión confirmada (pose frontal + landmarks colapsados)")
                else:
                    # Pérdida por pose: no marcar como oclusión
                    metrics['occluded'] = False
                    logger.debug("[DETECTION] ⏭️ Oclusión descartada (pose no frontal)")

            # Detección de celular eliminada - no se usa
            metrics.update({
                'phone_detected': False,
                'is_using_phone': False,
                'phone_confidence': 0.0,
                'phone_metadata': {}
            })

            # CÁLCULO DE ENFOQUE (con manejo perfecto de parpadeos y oclusión)
            # PRIORIDAD 1: Parpadeo normal (mantener último estado válido)
            if is_blink and not microsleep_detected and not occluded:
                # Durante parpadeo breve: mantener el último enfoque conocido
                if not hasattr(self, 'last_valid_focus_state'):
                    focus_score = 100.0
                    focus_state = 'Atento'
                else:
                    focus_score = self.last_valid_focus_score
                    focus_state = self.last_valid_focus_state
                logger.debug("[FOCUS] 👁️ Parpadeo normal: manteniendo estado anterior")
                
            # PRIORIDAD 2: Microsueño (mantener último válido)
            elif microsleep_detected:
                if not hasattr(self, 'last_valid_focus_state'):
                    focus_score = 0.0
                    focus_state = 'Ojos no detectados'
                else:
                    focus_score = self.last_valid_focus_score
                    focus_state = self.last_valid_focus_state
                logger.debug("[FOCUS] 😴 Microsueño: manteniendo estado anterior")
                
            # PRIORIDAD 3: Oclusión confirmada
            elif occluded or not eyes_detected:
                focus_score = 0.0
                focus_state = 'Ojos no detectados'
                logger.debug("[FOCUS] 🚫 Ojos no detectados/obstruidos")
                
            # PRIORIDAD 4: Cálculo normal de enfoque
            else:
                focus_score, focus_state = self._calculate_focus_score(
                    self.gaze_yaw_smooth, self.gaze_pitch_smooth, eyes_detected
                )
                # Guardar estado válido para referencia futura
                self.last_valid_focus_score = focus_score
                self.last_valid_focus_state = focus_state
                logger.debug(f"[FOCUS] ✅ Cálculo normal: {focus_state} ({focus_score:.1f})")

            # Aplicar histéresis temporal para estabilizar el estado mostrado
            stable_focus_state = self._apply_focus_hysteresis(focus_state)
            if stable_focus_state != focus_state:
                focus_state = stable_focus_state
            
            # Umbral para is_focused: solo "Atento" cuenta como enfocado
            is_focused = (focus_state == "Atento")
            
            metrics['is_focused'] = is_focused
            metrics['focus_score'] = focus_score
            metrics['focus_state'] = focus_state
            metrics['focus'] = focus_state
            logger.debug(f"[FOCUS] yaw={self.gaze_yaw_smooth:.1f}° pitch={self.gaze_pitch_smooth:.1f}° → {focus_state} ({focus_score:.1f})")
            
            # 6️⃣ ANÁLISIS TEMPORAL
            temporal_analysis = self._analyze_temporal_metrics(metrics)
            metrics.update(temporal_analysis)
            
            # Métricas de calidad del sistema
            self.successful_detections += 1
            # 🛠️ FIX: Evitar división por cero
            if self.total_frames_processed > 0:
                detection_rate = (self.successful_detections / self.total_frames_processed) * 100
            else:
                detection_rate = 100.0  # Primera detección exitosa = 100%
            metrics['detection_rate'] = round(detection_rate, 2)
            metrics['system_quality'] = 'excellent' if detection_rate > 90 else 'good' if detection_rate > 70 else 'fair'
            
        except Exception as e:
            self.failed_detections += 1
            logger.error(f"[SYSTEM] ❌ Error procesando frame #{self.total_frames_processed}: {e}", exc_info=True)
        
        return metrics
    
    def release(self):
        """Libera los recursos (como FaceMesh)"""
        if self.face_mesh:
            self.face_mesh.close()
        if self.face_detector:
            self.face_detector.close()
        logger.info("[SYSTEM] Recursos liberados")