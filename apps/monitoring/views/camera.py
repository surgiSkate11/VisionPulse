"""
Módulo para la gestión de cámara, detección de eventos faciales y manejo de la sesión.
Contiene las clases de puntos faciales y el gestor principal (CameraManager) 
que unifica la lógica.
"""

# =====================
# Imports
# =====================
import cv2
import mediapipe as mp
import numpy as np
import threading
import time
import logging
import os
from math import hypot
from dataclasses import dataclass
from typing import Optional, Dict, Any, Tuple
from django.utils import timezone
from ..models import MonitorSession, AlertEvent
from .improved_detector import UnifiedDetectionSystem

# =====================
# Configuración Global
# =====================

# Configuración de logging (reducir "ruido" de TF y MediaPipe)
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'
logging.getLogger('mediapipe').setLevel(logging.ERROR)

# Inicializar solución de MediaPipe
mp_face_mesh = mp.solutions.face_mesh

# =====================
# Data Classes (Puntos de Referencia)
# =====================

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

# =====================
# Clase: CameraManager (Gestor Principal - RESTAURADO)
# =====================

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
			# No borrar session_id al pausar, solo al terminar la sesión completamente
		self.pause_frame = None
		self.pause_metrics = None
		self.latest_metrics = {}
        
		# Almacenar configuración del usuario
		self.user_config = user_config
		# Almacenar configuración efectiva global+usuario
		self.effective_config = effective_config or {}
        
		# Inicializar el sistema unificado (que ahora contendrá los modelos avanzados)
		self.detection_system = UnifiedDetectionSystem(
			user_config=user_config, 
			effective_config=self.effective_config
		)

		self.blink_counter = 0
		self.last_frame_time = 0

		# Sin intervalo de frame artificial - procesar tan rápido como la cámara pueda
		self.frame_interval = 0

		# Control de frecuencia de análisis profundo
		if user_config and hasattr(user_config, 'monitoring_frequency'):
			self.analysis_interval = user_config.monitoring_frequency  # segundos
			print(f"[CAMERA] Frecuencia de análisis: cada {self.analysis_interval}s")
		else:
			self.analysis_interval = 30  # default: 30 segundos

		self.last_analysis_time = 0  # Timestamp del último análisis profundo

		# Inicializar contadores y objetivos de rendimiento
		self.error_count = 0
		self.max_errors = 3
		self.frames_processed = 0
		self.valid_detections = 0
		self.target_fps = 15.0
		self.low_fps_threshold = 12.0
		self.min_fps_threshold = 8.0

		# El bloque de carga de 'MultiModelDetector' se ha eliminado correctamente
		# ya que esa lógica ahora está DENTRO de UnifiedDetectionSystem.

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
					# Resetear contadores de rendimiento
					self.frames_processed = 0
					self.valid_detections = 0
					
					# 🔄 CRÍTICO: Resetear contador de parpadeos para nueva sesión
					self.blink_counter = 0
					if hasattr(self.detection_system, 'reset_session'):
						try:
							self.detection_system.reset_session()
							logging.info("[CAMERA] ✅ Sistema de detección reseteado para nueva sesión")
						except Exception as reset_error:
							logging.warning(f"[CAMERA] Error al resetear detector: {reset_error}")
					
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

			# No borrar session_id al pausar, solo al terminar la sesión completamente
			self.blink_counter = 0
			self.is_paused = False
			self.pause_frame = None
			self.pause_metrics = None
			
			# 🔄 RESETEAR detector de parpadeos interno
			if hasattr(self.detection_system, 'reset_session'):
				try:
					self.detection_system.reset_session()
					logging.info("[CAMERA] Sistema de detección reseteado")
				except Exception as reset_error:
					logging.warning(f"[CAMERA] Error al resetear detector: {reset_error}")

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
			return None, {'error': 'camera_not_initialized', 'is_running': self.is_running}
        
		# Retornar frame pausado si está en pausa
		if self.is_paused:
			if self.pause_frame is not None:
				logging.debug("[CAMERA] Retornando imagen de pausa")
			else:
				logging.warning("[CAMERA] is_paused=True pero pause_frame es None")
			return self.pause_frame, self.pause_metrics or {'status': 'paused'}

		# Calcular tiempo transcurrido (sin sleep artificial)
		time_since_last_frame = current_time - self.last_frame_time if self.last_frame_time > 0 else 0.033

		try:
			ret, frame = self.video.read()
			if not ret or frame is None:
				self.error_count += 1
				return None, {'error': 'frame_read_error'}

			# Validar dimensiones del frame antes de procesar
			if not self.validate_frame_dimensions(frame):
				self.error_count += 1
				return None, {'error': 'invalid_frame_dimensions'}

			# Contador de frames procesados
			self.frames_processed += 1


			# 🔥 PROCESAR CON SISTEMA UNIFICADO (que ahora tiene los modelos buenos)
			metrics = self.detection_system.process_frame(frame)

			# Contador de detecciones válidas
			if metrics.get('face_detected'):
				self.valid_detections += 1

			# Sincronizar contador de parpadeos desde ImprovedBlinkDetector
			detector_blink_count = getattr(self.detection_system.blink_detector, 'blink_counter', self.blink_counter)
			if detector_blink_count > self.blink_counter:
				self.blink_counter = detector_blink_count

			# Agregar métricas adicionales
			metrics.update({
				'total_blinks': self.blink_counter,
				'blink_count': self.blink_counter,  # Alias para compatibilidad
				'fps': 1.0 / time_since_last_frame if time_since_last_frame > 0.001 else 0.0,
				'error_count': self.error_count,
				'session_id': self.session_id,
				'detection_rate': (self.valid_detections / self.frames_processed) * 100.0 if self.frames_processed > 0 else 0.0,
			})

			# Ajuste dinámico de calidad DESHABILITADO - mantener calidad constante
			# try:
			# 	self._adjust_processing_quality(metrics.get('fps', 0.0))
			# except Exception:
			# 	pass

			# 🔥 ASEGURAR que eyes_detected esté presente
			if 'eyes_detected' not in metrics:
				metrics['eyes_detected'] = False

			# Actualizar métricas con thread safety
			with self._metrics_lock:
				self.latest_metrics = metrics

			self.last_frame_time = current_time
			self.error_count = 0

			return frame, metrics

		except Exception as e:
			logging.error(f"[CAMERA] Error procesando frame: {str(e)}", exc_info=True)
			return None, {'error': f'processing_error: {str(e)}'}

	def _adjust_processing_quality(self, fps: float):
		"""Ajusta escala de procesamiento y overlay para balancear precisión y rendimiento."""
		try:
			if not hasattr(self.detection_system, 'set_processing_scale'):
				logging.debug("[ADAPT] detection_system no soporta ajuste de calidad en runtime.")
				return

			if fps < self.min_fps_threshold:
				self.detection_system.set_processing_scale(0.5) 
				self.detection_system.set_overlay_enabled(False)
			elif fps < self.low_fps_threshold:
				self.detection_system.set_processing_scale(0.7) 
				self.detection_system.set_overlay_enabled(True)
			else:
				self.detection_system.set_processing_scale(1.0)
				self.detection_system.set_overlay_enabled(True)
                
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
				time_since_last_frame = current_time - self.last_frame_time
                
				if not isinstance(metrics, dict):
					logging.error("[METRICS] latest_metrics no es dict")
					metrics = {}

				# Agregar métricas adicionales
				metrics.update({
					'total_blinks': self.blink_counter,
					'camera_status': 'running' if self.is_running else 'stopped',
					'is_paused': self.is_paused,
					'error_count': self.error_count,
					'fps': 1.0 / time_since_last_frame if time_since_last_frame > 0.001 else 0,
					'system_time': current_time,
					'uptime': time_since_last_frame
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
    

