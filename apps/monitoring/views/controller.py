""""
Controller - Lógica de negocio y gestión de sesiones
Este módulo maneja el ciclo de vida completo de las sesiones de monitoreo
"""
import logging
# Minimizar salida de logs desde este módulo: solo errores
logging.getLogger().setLevel(logging.ERROR)
import os
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np
from django.conf import settings
from django.utils import timezone
from collections import deque

from ..models import (
    AlertEvent,
    AlertExerciseMapping,
    AlertTypeConfig,
    MonitorSession,
    SessionPause,
    get_effective_detection_config,
)
from apps.exercises.models import ExerciseSession
from ..utils.alert_detection import AlertDetectionEngine
from .advanced_metrics import AdvancedMetricsAnalyzer
from .camera import CameraManager
from apps.monitoring.models import AlertTypeConfig

class MonitoringController:
    """
    Controlador de sesiones de monitoreo con análisis avanzado.
    """

    def __init__(self):
        self.camera_manager = None
        self.metrics_analyzer = None
        self.lock = threading.Lock()
        self.session_lock = threading.Lock()
        self.metrics_cache = {}
        self.metrics_cache_time = 0
        self.metrics_cache_duration = 0.5
        self.alert_states = {}

        # Acumuladores para métricas
        self.ear_samples = []
        self.focus_samples = []
        self.head_yaw_samples = []
        self.head_pitch_samples = []
        self.head_roll_samples = []
        self.brightness_samples = []
        self.metrics_sample_count = 0
        self.total_frames_processed = 0
        
        # Calibración de baseline de head pose (primeros 10-15s de sesión)
        self.head_pose_baseline = {'yaw': None, 'pitch': None, 'calibrated': False}
        self.head_pose_calibration_samples = []
        self.head_pose_calibration_window = 15.0  # segundos
        
        # Control de recordatorios de descanso
        self.last_break_reminder = 0
        self.break_reminder_interval = 20 * 60
        self.user_config = None

        # Pausa automática por ejercicio
        self.paused_by_exercise = False
        self._last_checked_exercise_id = None
        self._paused_by_exercise_timestamp = None  # Timestamp de cuándo se pausó por ejercicio
        # Ventana de gracia al cerrar modal de ejercicio: evita re-pausa inmediata
        self.exercise_resume_grace_until = None

        # Pausa automática por AUSENCIA del usuario (3 repeticiones)
        self.paused_by_absence = False
        self.driver_absent_count = 0
        self.driver_absent_first_detection = None
        
        # Pausa automática por MÚLTIPLES PERSONAS (3 repeticiones)
        self.paused_by_multiple_people = False
        self.multiple_people_count = 0
        self.multiple_people_first_detection = None
        
        # Tracking para CÁMARA OBSTRUIDA (sin pausa automática, solo repetición)
        self.camera_occluded_count = 0
        self.camera_occluded_first_detection = None

        self.blink_history = deque(maxlen=1000)  # [(timestamp, ear), ...] para contar en ventana
        self.distraction_history = deque(maxlen=100)  # [(timestamp, duration), ...] eventos de distracción
        self.head_pose_history = deque(maxlen=360)  # [(timestamp, yaw, pitch), ...] para varianza (3 min @ 2 FPS)
        
        self._alert_tracking = {}
        self._last_alert_times = {}
        
        # EWMA para tasa de parpadeo
        self._blink_rate_ewma = 0.0
        
        # Tracking de distracción
        self._distraction_start_time = None
        self._was_distracted = False

        cfg = getattr(settings, 'MONITORING_ALERT_THRESHOLDS', {}) or {}

        # Umbrales de permanencia (segundos)
        self.distraction_duration_threshold = float(cfg.get('distraction_seconds', 3.0))
        self.low_light_duration_threshold = float(cfg.get('low_light_seconds', 5.0))
        self.driver_absent_duration_threshold = float(cfg.get('absent_seconds', 2.0))
        self.multiple_people_duration_threshold = float(cfg.get('multiple_people_seconds', 1.5))
        self.camera_occluded_duration_threshold = float(cfg.get('camera_occluded_seconds', 2.5))
        
        self.session_data = {
            'id': None,
            'start_time': None,
            'total_duration': 0,
            'effective_duration': 0,
            'pause_duration': 0,
            'alert_count': 0
        }

        # Cooldown por tipo de alerta (para evitar spam)
        self.alert_last_trigger_times = {}
        self.distract_min_interval = float(cfg.get('distract_min_interval', 30.0))  # segundos entre alertas de distracción

        # Inicializar motor de detección de alertas (SIN cooldown, histéresis selectiva)
        # Nota: La histéresis se configurará dinámicamente por usuario en start_session
        self.alert_engine = AlertDetectionEngine({
            # GRUPO A: Alertas CON ejercicio (7) - Sin histéresis
            'microsleep': {
                'sustain': 5.0,  # 5 segundos ojos cerrados (configurable por usuario)
                'use_hysteresis': False,
            },
            'fatigue': {
                'sustain': 10.0,  # 10 segundos con EAR bajo
                'use_hysteresis': False,
            },
            'low_blink_rate': {
                'sustain': 0.0,  # Evaluación instantánea después de 2 min
                'use_hysteresis': False,
            },
            'high_blink_rate': {
                'sustain': 0.0,  # Evaluación instantánea después de 2 min
                'use_hysteresis': False,
            },
            'frequent_distraction': {
                'sustain': 0.0,  # Sistema de conteo, no sustain
                'use_hysteresis': False,
            },
            'micro_rhythm': {
                'sustain': 0.0,  # Sistema de scoring, no sustain
                'use_hysteresis': False,
            },
            'head_tension': {
                'sustain': 0.0,  # Análisis de varianza, no sustain
                'use_hysteresis': False,
            },
            
            # GRUPO B: Alertas SIN ejercicio (3) - CON histéresis configurable por usuario
            'driver_absent': {
                'sustain': self.driver_absent_duration_threshold,  # 2s
                'use_hysteresis': True,
                'hysteresis': 3.0,  # Valor por defecto, se actualiza en start_session
            },
            'multiple_people': {
                'sustain': self.multiple_people_duration_threshold,  # 1.5s
                'use_hysteresis': True,
                'hysteresis': 3.0,  # Valor por defecto, se actualiza en start_session
            },
            'camera_occluded': {
                'sustain': self.camera_occluded_duration_threshold,  # 2.5s
                'use_hysteresis': True,
                'hysteresis': 3.0,  # Valor por defecto, se actualiza en start_session
            },
        })
    
    def start_session(self, user) -> Tuple[bool, Optional[str], Optional[MonitorSession]]:
        """Inicia una nueva sesión de monitoreo"""
        with self.session_lock:
            # Guardar configuración del usuario
            self.user_config = user
            
            # Configurar recordatorios de descanso
            logging.info(f"[BREAK-CONFIG] ===== CONFIGURANDO BREAK REMINDER =====")
            logging.info(f"[BREAK-CONFIG] Usuario: {user.username if user else 'None'}")
            logging.info(f"[BREAK-CONFIG] hasattr(user, 'monitoring_config'): {hasattr(user, 'monitoring_config')}")
            
            if hasattr(user, 'monitoring_config'):
                logging.info(f"[BREAK-CONFIG] user.monitoring_config: {user.monitoring_config}")
                if user.monitoring_config:
                    logging.info(f"[BREAK-CONFIG] hasattr(user.monitoring_config, 'break_reminder_interval'): {hasattr(user.monitoring_config, 'break_reminder_interval')}")
                    if hasattr(user.monitoring_config, 'break_reminder_interval'):
                        valor_minutos = user.monitoring_config.break_reminder_interval
                        logging.info(f"[BREAK-CONFIG] ✅ Valor leído del usuario: {valor_minutos} minutos")
                        self.break_reminder_interval = valor_minutos * 60  # convertir minutos a segundos
                        logging.info(f"[BREAK-CONFIG] ✅ break_reminder_interval configurado: {self.break_reminder_interval} segundos")
                    else:
                        logging.warning(f"[BREAK-CONFIG] ⚠️ monitoring_config no tiene break_reminder_interval")
                else:
                    logging.warning(f"[BREAK-CONFIG] ⚠️ monitoring_config es None")
            else:
                logging.warning(f"[BREAK-CONFIG] ⚠️ Usuario no tiene monitoring_config")
            
            logging.info(f"[BREAK-CONFIG] break_reminder_interval FINAL: {self.break_reminder_interval} segundos ({self.break_reminder_interval/60:.1f} minutos)")
            
            # 🔥 CRÍTICO: Resetear a 0 para contar desde inicio de sesión EFECTIVA
            self.last_break_reminder = 0
            logging.info(f"[BREAK-CONFIG] ✅ last_break_reminder reseteado a 0 (contará tiempo efectivo)")
            
            # Inicializar analizador de métricas avanzadas
            self.metrics_analyzer = AdvancedMetricsAnalyzer(window_duration=60)
            
            # Obtener configuración efectiva
            try:
                effective_cfg = get_effective_detection_config(user)
            except Exception as cfg_e:
                logging.error(f"[SESSION] Error al obtener config: {cfg_e}")
                effective_cfg = {}
            
            # 🔥 CRÍTICO: Actualizar histéresis del motor de alertas según configuración de usuario
            try:
                hysteresis_timeout = float(effective_cfg.get('hysteresis_timeout_seconds', 30.0))
                
                if hasattr(self, 'alert_engine') and self.alert_engine:
                    # Actualizar histéresis para las 3 alertas críticas
                    for alert_type in ['driver_absent', 'multiple_people', 'camera_occluded']:
                        if alert_type in self.alert_engine.config:
                            self.alert_engine.config[alert_type]['hysteresis'] = hysteresis_timeout
                else:
                    logging.warning(f"[SESSION] alert_engine no está disponible")
            except Exception as hyst_e:
                logging.error(f"[SESSION] Error actualizando histéresis: {hyst_e}", exc_info=True)

            if self.camera_manager is None:
                # Inicialización de cámara
                self.camera_manager = CameraManager(user_config=user, effective_config=effective_cfg)
            elif self.camera_manager.is_running:
                logging.warning("[SESSION] Sesión ya activa")
                return False, "Ya hay una sesión activa", None
            else:
                # Reinicialización de detector
                self.camera_manager.user_config = user
                try:
                    self.camera_manager.effective_config = effective_cfg
                except Exception:
                    pass
                
                if hasattr(user, 'sampling_interval_seconds') and user.sampling_interval_seconds:
                    self.camera_manager.frame_interval = user.sampling_interval_seconds / 30.0
                
                if hasattr(user, 'monitoring_frequency') and user.monitoring_frequency:
                    self.camera_manager.analysis_interval = user.monitoring_frequency

            try:
                # Cerrar sesiones sin finalizar
                unclosed_sessions = MonitorSession.objects.filter(
                    user=user,
                    end_time__isnull=True
                ).exists()

                if unclosed_sessions:
                    logging.warning("[SESSION] Cerrando sesiones sin finalizar previas")
                    MonitorSession.objects.filter(
                        user=user,
                        end_time__isnull=True
                    ).update(
                        end_time=timezone.now(),
                        status='interrupted'
                    )

                # Iniciar cámara
                if not self.camera_manager.start_camera():
                    error_msg = "No se pudo iniciar la cámara. Verifica que esté conectada y no esté en uso."
                    logging.error(f"[SESSION] {error_msg}")
                    return False, error_msg, None

                # Crear nueva sesión
                start_time = timezone.now()
                session = MonitorSession.objects.create(
                    user=user,
                    start_time=start_time,
                    status='active',
                    total_blinks=0,
                    alert_count=0
                )

                # Guardar metadata de la sesión
                try:
                    session.metadata = {
                        **(session.metadata or {}),
                        'effective_config': effective_cfg,
                    }
                    session.save(update_fields=['metadata'])
                except Exception as meta_e:
                    pass

                # Resetear acumuladores
                self.ear_samples = []
                self.focus_samples = []
                self.brightness_samples = []
                self.metrics_sample_count = 0
                self.total_frames_processed = 0
                
                # Resetear calibración de baseline
                self.head_pose_baseline = {'yaw': None, 'pitch': None, 'calibrated': False}
                self.head_pose_calibration_samples = []
                
                # 🔥 CRÍTICO: Resetear flags de pausa al iniciar sesión
                self.paused_by_absence = False
                self.paused_by_multiple_people = False
                self.paused_by_exercise = False
                self.driver_absent_count = 0
                self.multiple_people_count = 0
                self.camera_occluded_count = 0
                
                # Actualizar estado
                self.camera_manager.session_id = session.id
                self.session_data.update({
                    'id': session.id,
                    'start_time': start_time,
                    'total_duration': 0,
                    'effective_duration': 0,
                    'pause_duration': 0,
                    'alert_count': 0
                })
                
                return True, None, session

            except Exception as e:
                error_msg = f"Error al crear sesión: {str(e)}"
                logging.error(f"[SESSION] {error_msg}")
                logging.exception(e)

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
        self.metrics_cache.clear()
        self.metrics_cache_time = 0
        self.alert_states.clear()

        self.ear_samples = []
        self.focus_samples = []
        self.head_yaw_samples = []
        self.head_pitch_samples = []
        self.head_roll_samples = []
        self.brightness_samples = []
        self.metrics_sample_count = 0
        self.total_frames_processed = 0
        
        # Resetear calibración de baseline
        self.head_pose_baseline = {'yaw': None, 'pitch': None, 'calibrated': False}
        self.head_pose_calibration_samples = []
        
        # 🔥 CRÍTICO: Resetear flags de pausa
        self.paused_by_absence = False
        self.paused_by_multiple_people = False
        self.paused_by_exercise = False
        self.driver_absent_count = 0
        self.multiple_people_count = 0
        self.driver_absent_first_detection = None
        self.multiple_people_first_detection = None
        self.camera_occluded_count = 0
        self.camera_occluded_first_detection = None
        
        # Limpiar tracking de alertas
        self._alert_tracking.clear()
        self._last_alert_times.clear()
    
    def reload_user_config(self, user):
        """Recarga la configuración del usuario durante una sesión activa"""
        try:
            if self.camera_manager is None:
                logging.warning("[CONFIG] No hay sesión activa")
                return False, "No hay sesión activa"
            
            self.camera_manager.user_config = user
            self.user_config = user
            
            if hasattr(user, 'sampling_interval_seconds') and user.sampling_interval_seconds:
                self.camera_manager.frame_interval = user.sampling_interval_seconds / 30.0
            
            if hasattr(user, 'monitoring_frequency') and user.monitoring_frequency:
                self.alert_cooldown = float(user.monitoring_frequency)
            
            # Obtener configuración de monitoreo
            config = getattr(user, 'monitoring_config', None)
            if config:
                ear_value = config.ear_threshold
                # Actualizar break_reminder_interval
                if hasattr(config, 'break_reminder_interval'):
                    valor_minutos = config.break_reminder_interval
                    self.break_reminder_interval = valor_minutos * 60  # convertir a segundos
            else:
                ear_value = 0.20
            
            return True, "Configuración actualizada correctamente"
            
        except Exception as e:
            logging.error(f"[CONFIG] Error: {str(e)}")
            return False, f"Error: {str(e)}"
    
    def end_session(self) -> Tuple[bool, Optional[str], Dict[str, Any]]:
        """Finaliza la sesión actual y genera resumen de la sesión"""
        with self.session_lock:
            # Limpiar estados PRIMERO
            self.paused_by_exercise = False
            self._last_checked_exercise_id = None
            self._paused_by_exercise_timestamp = None
            self.exercise_resume_grace_until = None
            self.paused_by_absence = False
            self.paused_by_multiple_people = False
            
            if not self.camera_manager:
                logging.warning("[SESSION] Camera manager no existe")
                return True, "Sesión finalizada (sin manager)", {}
                
            if not self.camera_manager.is_running:
                logging.warning("[SESSION] Cámara ya detenida")
                return True, "Sesión finalizada (ya detenida)", {}

            try:
                session_summary = {}

                if self.camera_manager.session_id:
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

                        # Calcular promedios
                        avg_ear = None
                        avg_focus = None
                        avg_head_yaw = None
                        avg_head_pitch = None
                        avg_brightness = None

                        if self.ear_samples:
                            valid_ear_samples = [e for e in self.ear_samples if 0 < e <= 1.0]
                            if valid_ear_samples:
                                avg_ear = sum(valid_ear_samples) / len(valid_ear_samples)
                                avg_ear = float(max(0.0, min(1.0, avg_ear)))

                        if self.focus_samples:
                            focused_count = sum(1 for is_focused in self.focus_samples if is_focused)
                            avg_focus = (focused_count / len(self.focus_samples)) * 100.0
                            avg_focus = float(max(0.0, min(100.0, avg_focus)))

                        if self.brightness_samples:
                            valid_brightness = [b for b in self.brightness_samples if 0 <= b <= 255]
                            if valid_brightness:
                                avg_brightness = sum(valid_brightness) / len(valid_brightness)
                                avg_brightness = float(max(0.0, min(255.0, avg_brightness)))

                        if self.head_yaw_samples:
                            try:
                                valid = [v for v in self.head_yaw_samples if isinstance(v, (int, float)) and abs(v) <= 90]
                                if valid:
                                    avg_head_yaw = sum(valid) / len(valid)
                            except Exception:
                                pass

                        if self.head_pitch_samples:
                            try:
                                valid = [v for v in self.head_pitch_samples if isinstance(v, (int, float)) and abs(v) <= 90]
                                if valid:
                                    avg_head_pitch = sum(valid) / len(valid)
                            except Exception:
                                pass
                                
                        session.end_time = end_time
                        session.total_blinks = self.camera_manager.blink_counter
                        session.total_duration = total_duration
                        session.effective_duration = effective_duration
                        session.pause_duration = pause_duration
                        session.alert_count = self.session_data['alert_count']
                        session.avg_ear = avg_ear if avg_ear is not None else 0.0
                        session.focus_score = avg_focus if avg_focus is not None else 0.0
                        session.focus_percent = avg_focus if avg_focus is not None else 0.0
                        session.avg_focus_score = avg_focus if avg_focus is not None else 0.0
                        session.avg_brightness = avg_brightness if avg_brightness is not None else None
                        session.status = 'completed'
                        session.detection_rate = float(final_metrics.get('detection_rate', 0.0)) if final_metrics.get('detection_rate', None) is not None else 0.0
                        session.save()

                    except MonitorSession.DoesNotExist:
                        logging.error(f"[SESSION] Sesión {self.camera_manager.session_id} no encontrada")
                        return False, "Sesión no encontrada", {}

                # Limpieza
                self.camera_manager.stop_camera()
                self.reset_session_data()
                
                # IMPORTANTE: Limpiar caché de métricas al finalizar sesión
                self.metrics_cache = {}
                self.metrics_cache_time = time.time() - self.metrics_cache_duration - 1
                
                # Marcar alertas pendientes como auto-resueltas al finalizar sesión
                try:
                    if session:
                        AlertEvent.objects.filter(
                            session=session,
                            resolved_at__isnull=True
                        ).update(
                            resolved_at=timezone.now(),
                            resolution_method='auto'
                        )
                except Exception as alert_cleanup_error:
                    logging.error(f"[SESSION] Error limpiando alertas: {alert_cleanup_error}")

                return True, "Sesión finalizada correctamente", session_summary

            except Exception as e:
                error_msg = f"Error al finalizar sesión: {str(e)}"
                logging.error(f"[SESSION] {error_msg}")
                logging.exception(e)

                try:
                    self.camera_manager.stop_camera()
                    self.reset_session_data()
                except Exception as cleanup_error:
                    logging.error(f"[SESSION] Error en limpieza: {cleanup_error}")

                return False, error_msg, {}

    def pause_session(self) -> Tuple[bool, str, Dict[str, Any]]:
        """Pausa la sesión actual"""
        with self.lock:
            if not self.camera_manager or not self.camera_manager.is_running:
                return False, "No hay sesión activa", {}
            try:
                if not self.camera_manager.session_id:
                    return False, "No hay ID de sesión", {}
                session = MonitorSession.objects.get(id=self.camera_manager.session_id)
                
                # Verificar si ya está pausada
                existing_pause = session.pauses.filter(resume_time__isnull=True).first()
                if existing_pause:
                    return True, "La sesión ya está pausada", {
                        'is_paused': True,
                        'session_id': self.camera_manager.session_id,
                        'blink_count': self.camera_manager.blink_counter
                    }
                
                # Crear nueva entrada de pausa
                pause = SessionPause.objects.create(
                    session=session,
                    pause_time=timezone.now()
                )
                
                # LIBERAR LA CÁMARA al pausar para que se apague la luz
                if self.camera_manager.video and self.camera_manager.video.isOpened():
                    try:
                        self.camera_manager.video.release()
                    except Exception as e:
                        logging.error(f"[PAUSE] Error liberando cámara: {e}")
                
                # Mantener is_running=True para que get_metrics() funcione con datos en caché
                # pero marcar que está pausada para no intentar capturar frames
                self.camera_manager.is_paused = True
                
                # Buscar imagen de pausa
                possible_paths = [
                    os.path.join(settings.BASE_DIR, 'static', 'img', 'iconos', 'pausa.png'),
                    os.path.join(settings.BASE_DIR, 'static', 'img', 'pausa.png'),
                    os.path.join(settings.BASE_DIR, 'static', 'images', 'pausa.png'),
                    os.path.join(settings.STATICFILES_DIRS[0] if hasattr(settings, 'STATICFILES_DIRS') and settings.STATICFILES_DIRS else settings.BASE_DIR, 'img', 'iconos', 'pausa.png')
                ]
                
                h, w = 480, 640
                pause_frame_loaded = False
                pause_image = None
                pause_image_path = None
                
                for path in possible_paths:
                    if os.path.exists(path):
                        pause_image = cv2.imread(path, cv2.IMREAD_UNCHANGED)
                        if pause_image is not None:
                            pause_image_path = path
                            break
                
                if pause_image is not None:
                    if len(pause_image.shape) == 3 and pause_image.shape[2] == 4:
                        pause_image_resized = cv2.resize(pause_image, (w, h), interpolation=cv2.INTER_AREA)
                    else:
                        pause_image_resized = cv2.resize(pause_image, (w, h), interpolation=cv2.INTER_AREA)
                    
                    font = cv2.FONT_HERSHEY_SIMPLEX
                    text = "SESION EN PAUSA"
                    text_size = cv2.getTextSize(text, font, 1.5, 3)[0]
                    text_x = (w - text_size[0]) // 2
                    text_y = h // 2
                    
                    overlay = pause_image_resized.copy()
                    cv2.rectangle(overlay, (text_x - 30, text_y - text_size[1] - 30), 
                                (text_x + text_size[0] + 30, text_y + 30), (0, 0, 0), -1)
                    alpha = 0.7
                    pause_image_resized = cv2.addWeighted(overlay, alpha, pause_image_resized, 1 - alpha, 0)
                    
                    cv2.putText(pause_image_resized, text, (text_x, text_y), font, 1.5, (255, 255, 255), 3, cv2.LINE_AA)
                    sub_text = "Presiona 'Reanudar' para continuar"
                    sub_text_size = cv2.getTextSize(sub_text, font, 0.8, 2)[0]
                    sub_text_x = (w - sub_text_size[0]) // 2
                    sub_text_y = text_y + 60
                    cv2.putText(pause_image_resized, sub_text, (sub_text_x, sub_text_y), font, 0.8, (200, 200, 200), 2, cv2.LINE_AA)
                    
                    self.camera_manager.pause_frame = pause_image_resized
                    pause_frame_loaded = True
                    
                if not pause_frame_loaded:
                    pause_image_resized = np.zeros((h, w, 3), dtype=np.uint8)
                    font = cv2.FONT_HERSHEY_SIMPLEX
                    text = "SESION EN PAUSA"
                    text_size = cv2.getTextSize(text, font, 1.5, 3)[0]
                    text_x = (w - text_size[0]) // 2
                    text_y = h // 2
                    cv2.putText(pause_image_resized, text, (text_x, text_y), font, 1.5, (255, 255, 255), 3, cv2.LINE_AA)
                    sub_text = "Presiona 'Reanudar' para continuar"
                    sub_text_size = cv2.getTextSize(sub_text, font, 0.8, 2)[0]
                    sub_text_x = (w - sub_text_size[0]) // 2
                    sub_text_y = text_y + 60
                    cv2.putText(pause_image_resized, sub_text, (sub_text_x, sub_text_y), font, 0.8, (200, 200, 200), 2, cv2.LINE_AA)
                    self.camera_manager.pause_frame = pause_image_resized
                
                self.camera_manager.is_paused = True
                self.camera_manager.pause_metrics = {'status': 'paused', 'message': 'Sesión en pausa'}
                current_blinks = self.camera_manager.blink_counter
                session.total_blinks = current_blinks
                session.save(update_fields=['total_blinks'])
                
                # IMPORTANTE: Limpiar caché de métricas para que el siguiente polling devuelva datos frescos
                self.metrics_cache = {}
                self.metrics_cache_time = time.time() - self.metrics_cache_duration - 1
                
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
        """Reanuda la sesión actual y limpia flags de pausa crítica"""
        with self.lock:
            if not self.camera_manager or not self.camera_manager.session_id:
                return False, "No hay sesión activa", {}

            try:
                session = MonitorSession.objects.get(id=self.camera_manager.session_id)
                resume_time = timezone.now()

                # 1. Registrar la reanudación en BD
                current_pause = session.pauses.filter(resume_time__isnull=True).last()
                if current_pause:
                    current_pause.resume_time = resume_time
                    current_pause.save(update_fields=["resume_time"])

                # 2. Función auxiliar para limpiar estado de pausa
                def _clear_pause_state():
                    self.camera_manager.pause_frame = None
                    self.camera_manager.pause_metrics = None
                    self.camera_manager.is_paused = False
                    
                    # 🔥 CRÍTICO: Resetear ALL flags de auto-pausa
                    self.paused_by_exercise = False
                    self.paused_by_absence = False
                    self.paused_by_multiple_people = False
                    self.driver_absent_count = 0
                    self.multiple_people_count = 0
                    
                    # 🔥 CRÍTICO: Resetear tiempos de primera detección
                    self.driver_absent_first_detection = None
                    self.multiple_people_first_detection = None
                    
                    # 🔥 NUEVO: Limpiar cooldowns de alertas al reanudar
                    if hasattr(self, '_last_alert_times'):
                        self._last_alert_times.clear()
                    
                    # Limpiar motor de detección
                    if hasattr(self, 'alert_engine') and self.alert_engine:
                        for t in [AlertEvent.ALERT_DRIVER_ABSENT, AlertEvent.ALERT_MULTIPLE_PEOPLE, AlertEvent.ALERT_CAMERA_OCCLUDED]:
                            try:
                                self.alert_engine.resolve_alert(t)
                                logging.info(f"[RESUME] ✅ Alert engine resuelto: {t}")
                            except Exception as e:
                                logging.error(f"[RESUME] Error resolviendo {t}: {e}")
                    
                    # 🔥 NUEVO: Resolver alertas activas en BD al reanudar
                    try:
                        AlertEvent.objects.filter(
                            session=session,
                            resolved_at__isnull=True,
                            alert_type__in=[
                                AlertEvent.ALERT_DRIVER_ABSENT,
                                AlertEvent.ALERT_MULTIPLE_PEOPLE
                            ]
                        ).update(
                            resolved_at=resume_time,
                            resolution_method='manual_resume'
                        )
                    except Exception as resolve_e:
                        logging.error(f"[RESUME] Error resolviendo alertas: {resolve_e}")

                try:
                    # REABRIR LA CÁMARA al reanudar (si fue liberada en pause)
                    if not self.camera_manager.video or not self.camera_manager.video.isOpened():
                        camera_index = getattr(self.camera_manager, 'camera_index', 0)
                        self.camera_manager.video = cv2.VideoCapture(camera_index)
                        
                        if not self.camera_manager.video.isOpened():
                            raise Exception("No se pudo abrir la cámara")
                        
                        # Configurar la cámara
                        self.camera_manager.video.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                        self.camera_manager.video.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                        self.camera_manager.video.set(cv2.CAP_PROP_FPS, 30)
                    
                    # LIMPIAR FLAGS DE PAUSA INMEDIATAMENTE después de reabrir la cámara
                    self.camera_manager.is_paused = False
                    self.camera_manager.pause_frame = None
                    self.camera_manager.pause_metrics = None
                    
                    # Si la cámara no está corriendo (is_running=False), reiniciarla
                    if not self.camera_manager.is_running:
                        if not self.camera_manager.start_camera():
                            raise Exception("No se pudo iniciar el thread de la cámara")
                    
                    # Ahora sí, limpiar el resto del estado de pausa (alertas, eventos, etc.)
                    _clear_pause_state()

                except Exception as primary_error:
                    logging.error(f"[RESUME] Falló intento primario: {primary_error}")
                    # Fallback: reinicio completo
                    try:
                        self.camera_manager.stop_camera()
                        time.sleep(0.6)
                        
                        # Limpiar flags de pausa ANTES del reinicio
                        self.camera_manager.is_paused = False
                        self.camera_manager.pause_frame = None
                        self.camera_manager.pause_metrics = None
                        
                        if not self.camera_manager.start_camera():
                            raise Exception("Intento de reinicio completo falló")
                        _clear_pause_state()
                    except Exception as fallback_error:
                        logging.error(f"[RESUME] Fallback falló: {fallback_error}")
                        return False, f"Error al reanudar: {primary_error}; Reinicio alterno: {fallback_error}", {}

                # IMPORTANTE: Limpiar caché de métricas para que el siguiente polling devuelva datos frescos
                self.metrics_cache = {}
                self.metrics_cache_time = time.time() - self.metrics_cache_duration - 1

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
            
    
    def check_break_reminder(self) -> Optional[Dict[str, Any]]:
        """
        Verifica si es momento de recordar un descanso al usuario.
        Se dispara según el intervalo configurado en break_reminder_interval (UserMonitoringConfig).
        """
        if not self.user_config:
            return None
        
        # Si el intervalo es 0, el recordatorio está deshabilitado
        if self.break_reminder_interval <= 0:
            return None
        
        # No generar break_reminder si ya estamos pausados
        if self.camera_manager and self.camera_manager.is_paused:
            return None
        
        # Verificar si ya existe un break reminder activo (sin resolver)
        if self.camera_manager and self.camera_manager.session_id:
            try:
                from apps.monitoring.models import MonitorSession
                session = MonitorSession.objects.get(id=self.camera_manager.session_id)
                existing_break_reminder = AlertEvent.objects.filter(
                    session=session,
                    alert_type=AlertEvent.ALERT_BREAK_REMINDER,
                    resolved_at__isnull=True
                ).exists()
                
                if existing_break_reminder:
                    # Ya hay un recordatorio activo, no crear otro
                    return None
            except Exception as e:
                logging.error(f"[BREAK-REMINDER] Error verificando alerta existente: {e}")
        
        # Usar tiempo efectivo de monitoreo (no tiempo de reloj)
        effective_duration = self.session_data.get('effective_duration', 0)
        
        # Calcular tiempo efectivo desde el último break reminder
        time_since_last_break = effective_duration - self.last_break_reminder
        
        if time_since_last_break >= self.break_reminder_interval:
            minutes_worked = int(time_since_last_break / 60)
            
            # Actualizar el timestamp del último break reminder
            self.last_break_reminder = effective_duration
            
            return {
                'type': AlertEvent.ALERT_BREAK_REMINDER,
                'level': 'info',
                'message': f'¡Hora de descansar! Has trabajado {minutes_worked} minutos continuos',
                'timestamp': time.time(),
                'metadata': {
                    'minutes_worked': minutes_worked,
                    'effective_duration': effective_duration,
                    'recommended_break_duration': 5,
                    'requires_action': True,
                    'alert_priority': 'info'
                }
            }
        
        return None
    
    def _get_user_config(self) -> Dict[str, Any]:
        """Obtiene configuración del usuario de forma segura"""
        try:
            if self.camera_manager and self.camera_manager.session_id:
                session = MonitorSession.objects.select_related('user', 'user__monitoring_config').get(
                    id=self.camera_manager.session_id
                )
                user = session.user
                config = getattr(user, 'monitoring_config', None)
                
                if config:
                    fatigue_threshold = getattr(user, 'fatigue_threshold', 0.75)
                    return {
                        'fatigue_ear_threshold': config.ear_threshold * fatigue_threshold,
                        'low_blink_rate_threshold': config.low_blink_rate_threshold,
                        'high_blink_rate_threshold': config.high_blink_rate_threshold,
                        'low_light_threshold': config.low_light_threshold
                    }
        except Exception as e:
            logging.debug(f"[CONFIG] Usando valores por defecto: {str(e)}")

        # Valores por defecto
        return {
            'fatigue_ear_threshold': 0.15,
            'low_blink_rate_threshold': 10,
            'high_blink_rate_threshold': 35,
            'low_light_threshold': 70
        }

    def _reset_alert_states_on_absence(self):
        """Resetea estados de alerta cuando no hay persona presente"""
        self.alert_states[AlertEvent.ALERT_MULTIPLE_PEOPLE] = False
        self.alert_states[AlertEvent.ALERT_DISTRACT] = False
        self.alert_states[AlertEvent.ALERT_PHONE_USE] = False
        self.alert_states[AlertEvent.ALERT_CAMERA_OCCLUDED] = False
        # Limpiar estados temporales manejados ahora por el motor de detección
    
    def _register_blink(self, timestamp: float):
        """Registra un blink en la ventana deslizante"""
        self.blink_history.append((timestamp, 1))

    def _get_blink_count(self, current_time: float, window_seconds: float) -> int:
        """Cuenta blinks en la ventana deslizante [current_time - window_seconds, current_time]."""
        cutoff = current_time - float(window_seconds)
        return sum(1 for ts, _ in self.blink_history if ts >= cutoff)

    def _get_blink_rates(self, current_time: float) -> Dict[str, float]:
        """
        Calcula tasas de parpadeo por minuto usando ventanas deslizantes.
        - short: 30s
        - long: 120s
        También mantiene un EWMA de la tasa para mayor estabilidad.
        """
        short_window = 30.0
        long_window = 120.0
        short_count = self._get_blink_count(current_time, short_window)
        long_count = self._get_blink_count(current_time, long_window)
        short_rate = (short_count / short_window) * 60.0
        long_rate = (long_count / long_window) * 60.0

        # EWMA con alpha moderado
        if not hasattr(self, '_blink_rate_ewma'):
            self._blink_rate_ewma = long_rate
        alpha = 0.3
        self._blink_rate_ewma = alpha * long_rate + (1 - alpha) * self._blink_rate_ewma

        return {
            'short_rate': float(short_rate),
            'long_rate': float(long_rate),
            'ewma_rate': float(self._blink_rate_ewma)
        }
    
    def _register_distraction(self, timestamp: float, duration: float):
        """Registra un evento de distracción (mirando fuera 3-10s)"""
        if 3.0 <= duration <= 10.0:
            self.distraction_history.append((timestamp, duration))
            # Notificar al motor profesional para conteo en ventana móvil
            try:
                if hasattr(self, 'alert_engine') and self.alert_engine:
                    self.alert_engine.update('frequent_distraction', {'distraction_event': True}, timestamp=timestamp)
            except Exception:
                pass
    
    def _register_head_pose(self, timestamp: float, yaw: float, pitch: float):
        """Registra la pose de cabeza para análisis de varianza"""
        self.head_pose_history.append((timestamp, yaw, pitch))
    
    # ========================================================================
    # FUNCIONES INDIVIDUALES DE DETECCIÓN DE ALERTAS
    # ========================================================================
    
    def check_low_blink_rate_alert(self, current_time: float) -> Optional[Dict[str, Any]]:
        """
        Detecta tasa de parpadeo anormalmente baja con análisis avanzado.
        Prioridad: ALTA - Indica posible fatiga visual o concentración excesiva.
        
        Características:
        - Monitoreo dual: períodos cortos (30s) y largos (120s)
        - Análisis EWMA para tendencias
        - Score de severidad basado en desviación de tasa normal
        - Ejercicios de parpadeo consciente asociados
        
        🔥 v7.0: Threshold optimizado a < 12/min (antes 10/min era muy estricto)
        """
        if self.session_data.get('effective_duration', 0) < 90:  # 🔥 Reducido de 120s a 90s
            return None

        # 🔥 v7.0: Configuración optimizada
        user_cfg = self._get_user_config()
        low_thr = float(user_cfg.get('low_blink_rate_threshold', 12))  # 🔥 12/min (antes 10)

        # Usar configuración per-user
        effective_cfg = get_effective_detection_config(getattr(self, 'user_config', None) or getattr(self.camera_manager, 'user_config', None) or self.session_data.get('user')) if hasattr(self, 'user_config') or getattr(self.camera_manager, 'user_config', None) else {}
        detection_delay = effective_cfg.get('detection_delay_seconds', 30.0)
        cooldown = effective_cfg.get('alert_cooldown_seconds', 60.0)

        # Análisis de tasas de parpadeo
        rates = self._get_blink_rates(current_time)
        if not rates:
            return None
            
        short_rate = rates['short_rate']  # 30s
        long_rate = rates['long_rate']    # 120s
        ewma_rate = rates['ewma_rate']    # EWMA

        # Análisis de severidad
        normal_rate = 15.0  # Tasa normal de parpadeo/minuto
        severity_short = max(0, min(1, (normal_rate - short_rate) / normal_rate))
        severity_long = max(0, min(1, (normal_rate - long_rate) / normal_rate))
        severity_score = (severity_short * 0.3 + severity_long * 0.7) * 100

        # Datos enriquecidos para el motor
        low_blink_data = {
            'blink_rate': long_rate,
            'ewma_blink_rate': ewma_rate,
            'severity_score': severity_score,
            'detection_threshold': detection_delay,
            'cooldown': cooldown
        }
        
        result = self.alert_engine.update('low_blink_rate', low_blink_data, timestamp=current_time)
        if result == 'trigger':
            # Buscar ejercicio visual recomendado
            exercise_mapping = None
            try:
                from apps.monitoring.models import AlertExerciseMapping
                exercise_mapping = AlertExerciseMapping.objects.filter(
                    alert_type=AlertEvent.ALERT_LOW_BLINK_RATE,
                    is_active=True
                ).first()
            except Exception:
                pass

            return {
                'type': AlertEvent.ALERT_LOW_BLINK_RATE,
                'level': 'high',  # Actualizado a high por su importancia
                'timestamp': current_time,
                'metadata': {
                    'blink_rate_30s': short_rate,
                    'blink_rate_120s': long_rate,
                    'blink_rate_ewma': ewma_rate,
                    'threshold_low': low_thr,
                    'severity_score': severity_score,
                    'detection_delay': detection_delay,
                    'cooldown_seconds': cooldown,
                    'requires_exercise': True,
                    'has_exercise_mapping': bool(exercise_mapping),
                    'alert_priority': 'high',
                    'recommended_action': 'Realizar ejercicios de parpadeo consciente',
                    'analysis_window': {
                        'short_term': '30s',
                        'long_term': '120s',
                        'ewma_enabled': True
                    }
                }
            }
        return None
    
    def check_high_blink_rate_alert(self, current_time: float) -> Optional[Dict[str, Any]]:
        """
        Detecta tasa de parpadeo alta usando ventana deslizante (robusta).
        - Requiere >=120s de sesión
        - Usa ventana larga (120s) + corta (30s) para confirmar
        - Umbral por usuario (default alto 25/min, pero aquí usamos 40/min)
        """
        if self.session_data.get('effective_duration', 0) < 120:
            return None

        # Umbral “alto” acordado: > 40/min (deslizante 120s)
        high_thr = 40.0

        rates = self._get_blink_rates(current_time)
        short_rate = rates['short_rate']
        long_rate = rates['long_rate']

        # Condición: ventana larga por encima de 40/min, reforzada por corta > 35/min
        high_blink_data = {
            'blink_rate_120': long_rate,
            'blink_rate_30': short_rate
        }
        result = self.alert_engine.update('high_blink_rate', high_blink_data, timestamp=current_time)
        if result == 'trigger':
            # NO incluir 'message' - se obtiene del modelo AlertTypeConfig
            return {
                'type': AlertEvent.ALERT_HIGH_BLINK_RATE,
                'level': 'medium',
                'timestamp': current_time,
                'metadata': {
                    'blink_rate_30s': short_rate,
                    'blink_rate_120s': long_rate,
                    'threshold_high': high_thr,
                    'sustain_seconds': 30.0
                }
            }
        return None
    
    def check_frequent_distraction_alert(self, current_time: float) -> Optional[Dict[str, Any]]:
        """
        Detecta ráfagas de distracción: 4+ eventos cortos (3-10s) en 5 minutos.
        """
        # Contar distracciones en últimos 5 minutos
        distraction_event = False
        if self.distraction_history and self.distraction_history[-1][0] > current_time - 1:
            distraction_event = True
        result = self.alert_engine.update('frequent_distraction', {'distraction_event': distraction_event}, timestamp=current_time)
        if result == 'trigger':
            cutoff = current_time - 300  # 5 minutos
            distractions_in_window = sum(
                1 for ts, duration in self.distraction_history 
                if ts > cutoff
            )
            # NO incluir 'message' - se obtiene del modelo AlertTypeConfig
            return {
                'type': AlertEvent.ALERT_FREQUENT_DISTRACT,
                'level': 'medium',
                'timestamp': current_time,
                'metadata': {
                    'distraction_count': distractions_in_window,
                    'window_minutes': 5,
                    'threshold': 4
                }
            }
        return None
    
    def check_micro_rhythm_alert(self, metrics: Dict[str, Any], current_time: float) -> Optional[Dict[str, Any]]:
        """
        Sistema de scoring para detectar somnolencia temprana.
        Combina múltiples señales: EAR bajo, parpadeos lentos, cabeceo, blink rate.
        Threshold: score >= 50 puntos (ajustado sin bostezos).
        """
        score = 0
        details = {}
        avg_ear = metrics.get('avg_ear', 1.0)
        if 0 < avg_ear < 0.23:
            score += 30
            details['ear'] = avg_ear
        blink_duration_avg = metrics.get('blink_duration_avg', 0.0)
        if blink_duration_avg > 0.3:
            score += 30
            details['blink_duration'] = blink_duration_avg
        head_nod = metrics.get('head_nod_detected', False)
        head_pitch = metrics.get('head_pitch', 0.0)
        # Fix: Ensure head_pitch is not None before comparison
        if head_nod or (head_pitch is not None and head_pitch < -15):
            score += 25
            details['head_nod'] = True
            details['pitch'] = head_pitch
        blink_rate = metrics.get('blink_rate', 15.0)
        if blink_rate < 12:
            score += 15
            details['blink_rate'] = blink_rate
        result = self.alert_engine.update('micro_rhythm', {'score': score}, timestamp=current_time)
        if result == 'trigger':
            # NO incluir 'message' - se obtiene del modelo AlertTypeConfig
            return {
                'type': AlertEvent.ALERT_MICRO_RHYTHM,
                'level': 'medium',
                'timestamp': current_time,
                'metadata': {
                    'score': score,
                    'threshold': 50,
                    'details': details
                }
            }
        return None
    
    def check_head_tension_alert(self, current_time: float) -> Optional[Dict[str, Any]]:
        """
        Detecta rigidez postural por cabeza muy estática.
        Requiere 10+ minutos de sesión.
        Analiza varianza de pose en últimos 3 minutos con suavizado EMA.
        Usa baseline calibrado para calcular desviaciones relativas.
        Threshold: varianza < 2.0 grados desde baseline.
        """
        # Requiere mínimo 10 minutos de sesión
        if self.session_data.get('effective_duration', 0) < 600:
            return None
        
        # Calcular varianza de pose en últimos 3 minutos
        cutoff_3min = current_time - 180
        recent_poses = [
            (yaw, pitch) for ts, yaw, pitch in self.head_pose_history 
            if ts > cutoff_3min
        ]
        if len(recent_poses) < 10:
            return None
        
        # Aplicar suavizado EMA para eliminar ruido de alta frecuencia
        yaws_raw = [y for y, p in recent_poses]
        pitches_raw = [p for y, p in recent_poses]
        
        # EMA con alpha = 0.3 (70% historia, 30% actual)
        def apply_ema(values, alpha=0.3):
            if not values:
                return []
            smoothed = [values[0]]
            for v in values[1:]:
                smoothed.append(alpha * v + (1 - alpha) * smoothed[-1])
            return smoothed
        
        yaws_smooth = apply_ema(yaws_raw, alpha=0.3)
        pitches_smooth = apply_ema(pitches_raw, alpha=0.3)
        
        # Si hay baseline calibrado, calcular desviaciones relativas
        if self.head_pose_baseline['calibrated']:
            baseline_yaw = self.head_pose_baseline['yaw']
            baseline_pitch = self.head_pose_baseline['pitch']
            yaws_relative = [y - baseline_yaw for y in yaws_smooth]
            pitches_relative = [p - baseline_pitch for p in pitches_smooth]
            std_yaw = float(np.std(yaws_relative))
            std_pitch = float(np.std(pitches_relative))
        else:
            # Fallback: usar valores absolutos
            std_yaw = float(np.std(yaws_smooth))
            std_pitch = float(np.std(pitches_smooth))
        
        total_variance = std_yaw + std_pitch
        
        head_tension_data = {
            'std_yaw': std_yaw,
            'std_pitch': std_pitch,
            'session_time': self.session_data.get('effective_duration', 0)
        }
        result = self.alert_engine.update('head_tension', head_tension_data, timestamp=current_time)
        if result == 'trigger':
            # NO incluir 'message' - se obtiene del modelo AlertTypeConfig
            return {
                'type': AlertEvent.ALERT_HEAD_TENSION,
                'level': 'low',
                'timestamp': current_time,
                'metadata': {
                    'variance': total_variance,
                    'std_yaw': std_yaw,
                    'std_pitch': std_pitch,
                    'threshold': 2.0,
                    'samples': len(recent_poses),
                    'smoothed': True,
                    'baseline_calibrated': self.head_pose_baseline['calibrated'],
                    'baseline_yaw': self.head_pose_baseline.get('yaw', 0.0),
                    'baseline_pitch': self.head_pose_baseline.get('pitch', 0.0)
                }
            }
        return None
    
    def check_driver_absent_alert(self, faces_count: int, current_time: float) -> Optional[Dict[str, Any]]:
        """
        Detecta ausencia del usuario con tiempo configurable y sistema de histéresis mejorado.
        Prioridad: ALTA - Pausa automática después de una repetición si no se resuelve.
        
        Características:
        - Tiempo de detección configurable: 5-60 segundos
        - Sistema de histéresis de una sola repetición
        - Pausa automática si no se resuelve en tiempo configurable
        - Tracking detallado de eventos
        """
        effective_cfg = get_effective_detection_config(getattr(self, 'user_config', None) or getattr(self.camera_manager, 'user_config', None) or self.session_data.get('user')) if hasattr(self, 'user_config') or getattr(self.camera_manager, 'user_config', None) else {}
        detection_delay = effective_cfg.get('detection_delay_seconds', 5.0)
        hysteresis_timeout = effective_cfg.get('hysteresis_timeout_seconds', 30.0)
        # Una repetición (configurable si se agrega campo en user config en futuro)
        max_reps = 1
        
        
        # Si hay rostro, resetear detección
        if faces_count > 0:
            self.driver_absent_first_detection = None
            if self.alert_engine.is_active('driver_absent'):
                self._handle_hysteresis_resolution(AlertEvent.ALERT_DRIVER_ABSENT)
            return None

        # Iniciar o actualizar tiempo de primera detección
        current_dt = timezone.now()
        if self.driver_absent_first_detection is None:
            self.driver_absent_first_detection = current_dt
        
        # Calcular tiempo transcurrido
        detection_time = (current_dt - self.driver_absent_first_detection).total_seconds()

        # Datos enriquecidos para el motor
        driver_absent_data = {
            'face_detected': faces_count > 0,
            'detection_time': detection_time,
            'detection_threshold': detection_delay,
            'hysteresis_timeout': hysteresis_timeout
        }
        
        result = self.alert_engine.update('driver_absent', driver_absent_data, timestamp=current_time)
        
        # Gestionar alerta según resultado
        if (result == 'trigger' or self.alert_engine.is_active('driver_absent')) and detection_time >= detection_delay:
            if result == 'trigger':
                if not hasattr(self, 'driver_absent_count'):
                    self.driver_absent_count = 0
                self.driver_absent_count += 1
            
            count = getattr(self, 'driver_absent_count', 1)
            
            # Verificar si debemos pausar el monitoreo
            should_pause = (detection_time > hysteresis_timeout and count >= max_reps)
            if should_pause:
                self.pause_session()

            return {
                'type': AlertEvent.ALERT_DRIVER_ABSENT,
                'level': 'high',
                'timestamp': current_time,
                'metadata': {
                    'faces': faces_count,
                    'repetition_count': count,
                    'detection_time': detection_time,
                    'detection_delay': detection_delay,
                    'hysteresis_timeout': hysteresis_timeout,
                    'max_repetitions': max_reps,
                    'first_detection': self.driver_absent_first_detection.isoformat(),
                    'auto_paused': should_pause,
                    'alert_priority': 'high'
                }
            }
        elif result == 'resolve':
            self._handle_hysteresis_resolution(AlertEvent.ALERT_DRIVER_ABSENT)
            self.driver_absent_first_detection = None
        
        return None
    
    def check_multiple_people_alert(self, faces_count: int, multiple_faces: bool, 
    current_time: float) -> Optional[Dict[str, Any]]:
        """
        Detecta múltiples personas con tiempo configurable y sistema de histéresis mejorado.
        Prioridad: ALTA - Pausa automática después de una repetición si no se resuelve.
        
        Características:
        - Tiempo de detección configurable: 5-60 segundos
        - Sistema de histéresis de una sola repetición
        - Pausa automática si no se resuelve en tiempo configurable
        - Tracking detallado de presencia múltiple
        """
        effective_cfg = get_effective_detection_config(getattr(self, 'user_config', None) or getattr(self.camera_manager, 'user_config', None) or self.session_data.get('user')) if hasattr(self, 'user_config') or getattr(self.camera_manager, 'user_config', None) else {}
        detection_delay = effective_cfg.get('detection_delay_seconds', 5.0)
        hysteresis_timeout = effective_cfg.get('hysteresis_timeout_seconds', 30.0)
        max_reps = 1

        # Control de primera detección
        if not hasattr(self, 'multiple_people_first_detection'):
            self.multiple_people_first_detection = None
        
        # Si hay solo un rostro o ninguno, resetear detección
        if faces_count <= 1:
            self.multiple_people_first_detection = None
            if self.alert_engine.is_active('multiple_people'):
                self._handle_hysteresis_resolution(AlertEvent.ALERT_MULTIPLE_PEOPLE)
            return None

        # Iniciar o actualizar tiempo de primera detección
        current_dt = timezone.now()
        if self.multiple_people_first_detection is None:
            self.multiple_people_first_detection = current_dt
        
        # Calcular tiempo transcurrido
        detection_time = (current_dt - self.multiple_people_first_detection).total_seconds()

        # Datos enriquecidos para el motor
        multiple_data = {
            'num_faces': faces_count,
            'detection_time': detection_time,
            'detection_threshold': detection_delay,
            'hysteresis_timeout': hysteresis_timeout
        }
        
        result = self.alert_engine.update('multiple_people', multiple_data, timestamp=current_time)
        
        # Gestionar alerta según resultado
        if (result == 'trigger' or self.alert_engine.is_active('multiple_people')) and detection_time >= detection_delay:
            # 🔥 CRÍTICO: Solo incrementar contador cuando result == 'trigger' (igual que driver_absent)
            if result == 'trigger':
                if not hasattr(self, 'multiple_people_count'):
                    self.multiple_people_count = 0
                self.multiple_people_count += 1
            
            count = getattr(self, 'multiple_people_count', 1)
            
            # Verificar si debemos pausar el monitoreo
            should_pause = (detection_time > hysteresis_timeout and count >= max_reps)
            if should_pause:
                self.pause_session()

            return {
                'type': AlertEvent.ALERT_MULTIPLE_PEOPLE,
                'level': 'high',
                'timestamp': current_time,
                'metadata': {
                    'faces': faces_count,
                    'multiple_faces_flag': multiple_faces,
                    'repetition_count': count,
                    'detection_time': detection_time,
                    'detection_delay': detection_delay,
                    'hysteresis_timeout': hysteresis_timeout,
                    'max_repetitions': max_reps,
                    'first_detection': self.multiple_people_first_detection.isoformat(),
                    'auto_paused': should_pause,
                    'alert_priority': 'high'
                }
            }
        elif result == 'resolve':
            self._handle_hysteresis_resolution(AlertEvent.ALERT_MULTIPLE_PEOPLE)
            self.multiple_people_first_detection = None
        
        return None
    
    def check_microsleep_alert(self, microsleep_condition: bool, frames_closed: float, 
                               current_time: float) -> Optional[Dict[str, Any]]:
        """
        Detecta microsueño con configuración dinámica y ejercicios de reactivación.
        Prioridad: CRÍTICA - Requiere atención inmediata.
        """
        effective_cfg = get_effective_detection_config(getattr(self, 'user_config', None) or getattr(self.camera_manager, 'user_config', None) or self.session_data.get('user')) if hasattr(self, 'user_config') or getattr(self.camera_manager, 'user_config', None) else {}
        microsleep_threshold = effective_cfg.get('microsleep_duration_seconds', 5.0)
        
        # 🔥 LOG: Confirmar threshold configurado por el usuario
        if microsleep_condition and frames_closed > 0:
            print(f"[MICROSLEEP] 👁️ Ojos cerrados: {frames_closed:.2f}s / Threshold usuario: {microsleep_threshold}s")

        # Alimentar el motor con condición y umbral configurado
        microsleep_data = {
            'eyes_closed': bool(microsleep_condition),
            'threshold': microsleep_threshold  # 🔥 CLAVE: Se pasa al motor para uso dinámico
        }
        result = self.alert_engine.update('microsleep', microsleep_data, timestamp=current_time)
        
        if result == 'trigger':
            # Buscar ejercicio asociado para reactivación
            exercise_mapping = None
            try:
                from apps.monitoring.models import AlertExerciseMapping
                exercise_mapping = AlertExerciseMapping.objects.filter(
                    alert_type=AlertEvent.ALERT_MICROSLEEP,
                    is_active=True
                ).first()
            except Exception:
                pass

            # Calcular métricas adicionales
            detection_confidence = min(1.0, frames_closed / microsleep_threshold)
            risk_level = 'high' if detection_confidence > 0.8 else 'medium'

            return {
                'type': AlertEvent.ALERT_MICROSLEEP,
                'level': 'critical',
                'timestamp': current_time,
                'metadata': {
                    'duration_seconds': frames_closed,
                    'threshold_seconds': microsleep_threshold,
                    'is_microsleep': True,
                    'requires_exercise': True,
                    'has_exercise_mapping': bool(exercise_mapping),
                    'detection_confidence': detection_confidence,
                    'risk_level': risk_level,
                    'sustained_detection': frames_closed > microsleep_threshold
                }
            }
        
        return None
    
    def check_camera_occluded_alert(self, faces_count: int, eyes_detected: bool, 
                                    eyes_closed: bool, microsleep_active: bool,
                                    occluded_flag: Optional[bool], 
                                    current_time: float) -> Optional[Dict[str, Any]]:
        """
        Detecta cuando un objeto bloquea la visión de los ojos.
        Usa histéresis configurable por usuario (hysteresis_timeout_seconds).
        Si la histéresis no resuelve la alerta, vuelve a sonar según alert_repeat_interval.
        Condición: rostro presente + ojos no detectados + NO ojos cerrados + NO microsueño.
        """
        # Aplicar restricción de pose: solo considerar oclusión si la cabeza está casi frontal
        yaw = 0.0
        pitch = 0.0
        occlusion_candidate = None
        try:
            latest = self.camera_manager.get_latest_metrics() if self.camera_manager else {}
            yaw = float(latest.get('head_yaw', 0.0))
            pitch = float(latest.get('head_pitch', 0.0))
            occlusion_candidate = latest.get('occlusion_candidate', latest.get('occluded_candidate', None))
        except Exception:
            pass
        frontal = (abs(yaw) <= 25.0) and (abs(pitch) <= 20.0)
        
        # Fallback robusto: inferir oclusión cuando hay rostro presente, ojos NO detectados, 
        # NO ojos cerrados, NO microsueño
        inferred_occlusion = (faces_count > 0) and (not eyes_detected) and (not eyes_closed) and (not microsleep_active)
        candidate_true = (occlusion_candidate is True)
        flag_true = (occluded_flag is True)
        
        print(f"\n🔍 [OCCLUDED] INPUTS: faces={faces_count}, eyes_det={eyes_detected}, eyes_closed={eyes_closed}, microsleep={microsleep_active}")
        print(f"🔍 [OCCLUDED] INPUTS: occluded_flag={occluded_flag}, candidate={occlusion_candidate}")
        print(f"🔍 [OCCLUDED] INFERRED: {faces_count} > 0 AND NOT {eyes_detected} AND NOT {eyes_closed} AND NOT {microsleep_active} = {inferred_occlusion}\n")
        
        # 🔥 IMPORTANTE: La condición debe ser consistente con lo que el MOTOR espera
        # El motor de histéresis requiere que la condición sea True/False de forma estable
        # Para camera_occluded: condition = frontal AND (flag OR candidate OR inferred)
        # INFERRED se activa cuando: hay rostro PERO no hay ojos Y no están cerrados Y no es microsueño
        occlusion_effective = frontal and (flag_true or candidate_true or inferred_occlusion)
        
        print(f"\n📊 [OCCLUDED] CÁLCULO: frontal={frontal}, flag={flag_true}, candidate={candidate_true}, inferred={inferred_occlusion}")
        print(f"📊 [OCCLUDED] RESULTADO: occlusion_effective={occlusion_effective}\n")
        
        # 🎯 NO forzar a False cuando eyes_detected=True porque eso crea un círculo vicioso
        # La detección de ojos puede fallar cuando hay oclusión real, así que confiamos en:
        # 1. occluded_flag (del modelo)
        # 2. occlusion_candidate (del modelo)  
        # 3. inferred_occlusion (nuestra inferencia: rostro sin ojos, no cerrados, no microsueño)
        
        # El motor entonces manejará la histéresis automáticamente cuando condition cambie

        # Si no hay oclusión, resetear contador y primera detección
        if not occlusion_effective:
            self.camera_occluded_first_detection = None
            self.camera_occluded_count = 0
        
        # Iniciar o actualizar tiempo de primera detección
        current_dt = timezone.now()
        if occlusion_effective and self.camera_occluded_first_detection is None:
            self.camera_occluded_first_detection = current_dt
        
        # El motor evalúa la condición con estas señales, incluyendo histéresis
        camera_occluded_data = {
            'face_detected': faces_count > 0,
            'eyes_detected': bool(eyes_detected),
            'eyes_closed': bool(eyes_closed),
            'microsleep_active': bool(microsleep_active),
            'occlusion_flag': occlusion_effective,
            'condition': occlusion_effective
        }
        
        result = self.alert_engine.update('camera_occluded', camera_occluded_data, timestamp=current_time)
        is_active = self.alert_engine.is_active('camera_occluded')
        
        # Incrementar contador SOLO cuando se dispara por primera vez (trigger)
        if result == 'trigger':
            self.camera_occluded_count += 1
        
        # Retornar alerta mientras esté ACTIVA
        if is_active:
            count = self.camera_occluded_count
            detection_time = 0
            if self.camera_occluded_first_detection:
                detection_time = (current_dt - self.camera_occluded_first_detection).total_seconds()
            
            # NO incluir 'message' - se obtiene del modelo AlertTypeConfig
            return {
                'type': AlertEvent.ALERT_CAMERA_OCCLUDED,
                'level': 'medium',
                'timestamp': current_time,
                'metadata': {
                    'faces': faces_count,
                    'eyes_detected': False,
                    'occluded': True,
                    'head_yaw': yaw,
                    'head_pitch': pitch,
                    'occlusion_candidate': bool(occlusion_candidate is True),
                    'derived_by_fallback': bool(not flag_true and (candidate_true or inferred_occlusion)),
                    'repetition_count': count,
                    'detection_time': detection_time,
                    'first_detection': self.camera_occluded_first_detection.isoformat() if self.camera_occluded_first_detection else None
                }
            }
        elif result == 'resolve':
            self._handle_hysteresis_resolution(AlertEvent.ALERT_CAMERA_OCCLUDED)
            self.camera_occluded_first_detection = None
            self.camera_occluded_count = 0
            self._last_alert_times.pop(AlertEvent.ALERT_CAMERA_OCCLUDED, None)
        
        return None
    
    def check_fatigue_alert(self, avg_ear: float, blink_rate: float, 
                           microsleep_active: bool, fatigue_threshold: float,
                           current_time: float) -> Optional[Dict[str, Any]]:
        """
        Detecta fatiga visual mediante análisis avanzado de EAR y patrones de parpadeo.
        Prioridad: CRÍTICA - Monitoreo continuo con análisis de patrones.
        """
        # Validación de datos de entrada
        if not (0 < avg_ear <= 1.0):
            return None
        
        if microsleep_active:
            return None
        
        # Análisis de patrones de parpadeo
        try:
            rates = self._get_blink_rates(current_time)
            blink_rate_recent = float(rates.get('ewma_rate', rates.get('short_rate', blink_rate)))
            blink_history = rates.get('history', [])
            
            # Análisis de variabilidad
            if len(blink_history) >= 3:
                import numpy as np
                blink_variance = np.var([r[1] for r in blink_history[-10:]])
                pattern_irregularity = blink_variance > 0.5
            else:
                blink_variance = 0
                pattern_irregularity = False
                
        except Exception as e:
            logging.warning(f"Error en análisis de parpadeo: {e}")
            blink_rate_recent = float(blink_rate)
            blink_variance = 0
            pattern_irregularity = False

        effective_cfg = get_effective_detection_config(getattr(self, 'user_config', None) or getattr(self.camera_manager, 'user_config', None) or self.session_data.get('user')) if hasattr(self, 'user_config') or getattr(self.camera_manager, 'user_config', None) else {}
        cooldown = effective_cfg.get('alert_cooldown_seconds', 60.0)
        detection_threshold = effective_cfg.get('detection_delay_seconds', 10.0)

        # Cálculo de score de fatiga (0-100)
        ear_factor = max(0, min(1, (fatigue_threshold - avg_ear) / (fatigue_threshold * 0.5)))
        blink_factor = max(0, min(1, abs(blink_rate_recent - 15) / 10))  # 15 es la tasa ideal
        pattern_factor = 0.3 if pattern_irregularity else 0
        
        fatigue_score = (ear_factor * 0.5 + blink_factor * 0.3 + pattern_factor * 0.2) * 100

        # Datos enriquecidos para el motor de alertas
        fatigue_data = {
            'ear': float(avg_ear),
            'blink_rate': blink_rate_recent,
            'microsleep_active': bool(microsleep_active),
            'fatigue_score': fatigue_score,
            'detection_threshold': detection_threshold,
            'cooldown': cooldown
        }
        
        result = self.alert_engine.update('fatigue', fatigue_data, timestamp=current_time)
        
        if result == 'trigger':
            # Buscar ejercicio visual recomendado
            exercise_mapping = None
            try:
                from apps.monitoring.models import AlertExerciseMapping
                exercise_mapping = AlertExerciseMapping.objects.filter(
                    alert_type=AlertEvent.ALERT_FATIGUE,
                    is_active=True
                ).first()
            except Exception:
                pass

            return {
                'type': AlertEvent.ALERT_FATIGUE,
                'level': 'high',
                'timestamp': current_time,
                'metadata': {
                    'ear': avg_ear,
                    'threshold': fatigue_threshold,
                    'blink_rate': blink_rate_recent,
                    'blink_variance': blink_variance,
                    'pattern_irregular': pattern_irregularity,
                    'fatigue_score': fatigue_score,
                    'requires_exercise': True,
                    'has_exercise_mapping': bool(exercise_mapping),
                    'detection_time': detection_threshold,
                    'cooldown_seconds': cooldown,
                    'is_fatigue': True,
                    'alert_priority': 'critical'
                }
            }
        
        return None
    
    def _handle_hysteresis_resolution(self, alert_type: str):
        """
        Maneja la resolución automática de una alerta por histéresis:
        1. Marca la alerta como resuelta en BD
        2. Actualiza tracking de repeticiones y estado
        3. Prepara para permitir nueva ocurrencia si la condición vuelve
        
        Args:
            alert_type: Tipo de alerta que se resolvió automáticamente
        """
        try:
            if not self.camera_manager or not self.camera_manager.session_id:
                print(f"⚠️ [HYSTERESIS-RESOLVE] No hay camera_manager o session_id")
                return
            
            current_time = timezone.now()
            
            print(f"\n🔍 [HYSTERESIS-RESOLVE] Buscando alerta activa de tipo {alert_type}")
            
            # Buscar alerta activa para resolver
            recent_alert = AlertEvent.objects.filter(
                session_id=self.camera_manager.session_id,
                alert_type=alert_type,
                resolved_at__isnull=True
            ).order_by('-triggered_at').first()
            
            if recent_alert:
                print(f"✅ [HYSTERESIS-RESOLVE] Encontrada alerta #{recent_alert.id}, actualizando...")
                
                # 1. Marcar como resuelta
                recent_alert.resolved_at = current_time
                recent_alert.resolution_method = 'hysteresis'
                
                # Actualizar metadata con información de resolución
                meta = recent_alert.metadata or {}
                meta.update({
                    'resolved_by_hysteresis': True,
                    'hysteresis_resolution_time': current_time.isoformat(),
                    'total_duration_seconds': (current_time - recent_alert.triggered_at).total_seconds()
                })
                recent_alert.metadata = meta
                recent_alert.save()
                
                recent_alert.refresh_from_db()
                print(f"GUARDADO: AlertEvent #{recent_alert.id}, resolved_at={recent_alert.resolved_at}, method={recent_alert.resolution_method}")
                
                logging.info(f"[HYSTERESIS-RESOLVE] AlertEvent #{recent_alert.id} marcada como resuelta en BD")
                
                print(f"� [HYSTERESIS-RESOLVE] AlertEvent #{recent_alert.id} guardada en BD")
                print(f"💾 [HYSTERESIS-RESOLVE] resolved_at={recent_alert.resolved_at}")
                print(f"💾 [HYSTERESIS-RESOLVE] resolution_method={recent_alert.resolution_method}\n")
                
                logging.info(f"[HYSTERESIS-RESOLVE] ✅ AlertEvent #{recent_alert.id} marcada como resuelta en BD")
                logging.info(f"[HYSTERESIS-RESOLVE] resolved_at={recent_alert.resolved_at}, method={recent_alert.resolution_method}")
                
                # 2. Resetear contadores cuando se resuelve por histéresis
                # Esto es correcto porque la condición ya no existe
                if alert_type == AlertEvent.ALERT_DRIVER_ABSENT:
                    self.driver_absent_count = 0
                elif alert_type == AlertEvent.ALERT_MULTIPLE_PEOPLE:
                    self.multiple_people_count = 0
                
                # 3. Actualizar tracking
                tracking = self._alert_tracking.get(alert_type, {})
                if tracking:
                    tracking.update({
                        'last_resolution_time': current_time,
                        'last_resolution_method': 'hysteresis',
                        'resolved_alert_id': recent_alert.id,
                        'repetition_count': 0  # Resetear conteo para todas las alertas
                    })
                    # Tracking reseteado
                
                # 4. Notificar al motor de detección
                try:
                    if hasattr(self, 'alert_engine') and self.alert_engine:
                        self.alert_engine.resolve_alert(alert_type)
                except Exception as engine_e:
                    logging.error(f"[ALERT-ENGINE] Error al desactivar {alert_type}: {engine_e}")
            
            else:
                # No se encontró alerta activa para resolver
                print(f"⚠️ [HYSTERESIS-RESOLVE] NO se encontró alerta activa de tipo {alert_type}")
                logging.warning(f"[HYSTERESIS-RESOLVE] No se encontró alerta activa para resolver: {alert_type}")
        
        except Exception as e:
            print(f"❌ [HYSTERESIS-RESOLVE] ERROR: {str(e)}")
            logging.error(f"[ALERT] Error en resolución por histéresis para {alert_type}: {str(e)}")
            logging.exception(e)
    
    def _should_pause_on_driver_absent(self) -> bool:
        """Verifica si se debe pausar la sesión por ausencias repetidas."""
        return hasattr(self, 'driver_absent_count') and self.driver_absent_count >= 3
    
    def _should_pause_on_multiple_people(self) -> bool:
        """Verifica si se debe pausar la sesión por múltiples personas repetidas."""
        return hasattr(self, 'multiple_people_count') and self.multiple_people_count >= 3
    
    def auto_pause_driver_absent(self) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Pausa la sesión automáticamente debido a usuario ausente.
        Versión pública para ser llamada desde el API.
        
        Returns:
            Tuple[bool, str, Dict]: (success, message, data)
        """
        try:
            ok, msg, pause_data = self.pause_session()
            if ok:
                current_time = timezone.now()
                self.paused_by_absence = True
                logging.warning("[SESSION] Pausa automática por usuario ausente")
                
                try:
                    if hasattr(self, 'alert_engine') and self.alert_engine:
                        self.alert_engine.resolve_alert(AlertEvent.ALERT_DRIVER_ABSENT)
                except Exception as engine_e:
                    logging.error(f"[ALERT-ENGINE] Error desactivando driver_absent: {engine_e}")
                    
                try:
                    if self.camera_manager and self.camera_manager.session_id:
                        recent_event = AlertEvent.objects.filter(
                            session_id=self.camera_manager.session_id,
                            alert_type=AlertEvent.ALERT_DRIVER_ABSENT,
                            resolved_at__isnull=True
                        ).order_by('-triggered_at').first()
                        
                        if recent_event:
                            # Marcar como resuelta con detalles
                            meta = recent_event.metadata or {}
                            meta.update({
                                'auto_paused_after_repetitions': True,
                                'repetition_limit_reached': True,
                                'resolved_by_auto_pause': True,
                                'resolution_time': current_time.isoformat(),
                                'total_duration_seconds': (current_time - recent_event.triggered_at).total_seconds()
                            })
                            recent_event.resolved_at = current_time
                            recent_event.resolution_method = 'auto_pause'
                            recent_event.metadata = meta
                            recent_event.save(update_fields=['resolved_at', 'resolution_method', 'metadata'])
                            
                            logging.info(f"[ALERT] ✓ Alerta {recent_event.id} resuelta por auto-pausa")
                            
                            # Actualizar tracking
                            tracking = self._alert_tracking.get(AlertEvent.ALERT_DRIVER_ABSENT, {})
                            if tracking:
                                tracking.update({
                                    'last_resolution_time': current_time,
                                    'last_resolution_method': 'auto_pause',
                                    'resolved_alert_id': recent_event.id
                                })
                except Exception as db_e:
                    logging.error(f"[ALERT] Error actualizando alerta por auto-pausa: {db_e}")
                
                return True, "Monitoreo pausado por usuario ausente", pause_data
            else:
                logging.warning(f"[SESSION] No se pudo pausar por ausencia: {msg}")
                return False, msg, {}
        except Exception as e:
            logging.error(f"[SESSION] Error al pausar por ausencia: {str(e)}", exc_info=True)
            return False, str(e), {}
    
    def _pause_session_due_to_absence(self):
        """Pausa la sesión debido a 3 ausencias del conductor.
        Debe pausar el procesamiento (cámara) y dejar trazabilidad de la causa.
        """
        try:
            ok, msg, _ = self.pause_session()
            if ok:
                current_time = timezone.now()
                self.paused_by_absence = True
                logging.warning("[SESSION] Pausa automática por ausencias repetidas")
                
                try:
                    if hasattr(self, 'alert_engine') and self.alert_engine:
                        self.alert_engine.resolve_alert(AlertEvent.ALERT_DRIVER_ABSENT)
                except Exception as engine_e:
                    logging.error(f"[ALERT-ENGINE] Error desactivando driver_absent: {engine_e}")
                try:
                    if self.camera_manager and self.camera_manager.session_id:
                        recent_event = AlertEvent.objects.filter(
                            session_id=self.camera_manager.session_id,
                            alert_type=AlertEvent.ALERT_DRIVER_ABSENT,
                            resolved_at__isnull=True
                        ).order_by('-triggered_at').first()
                        
                        if recent_event:
                            # Marcar como resuelta con detalles
                            meta = recent_event.metadata or {}
                            meta.update({
                                'auto_paused_after_repetitions': True,
                                'repetition_limit_reached': True,
                                'repetition_count': 3,
                                'resolved_by_auto_pause': True,
                                'resolution_time': current_time.isoformat(),
                                'total_duration_seconds': (current_time - recent_event.triggered_at).total_seconds()
                            })
                            recent_event.resolved_at = current_time
                            recent_event.resolution_method = 'auto_pause'
                            recent_event.metadata = meta
                            recent_event.save(update_fields=['resolved_at', 'resolution_method', 'metadata'])
                            
                            # Resuelto por auto-pausa
                            
                            # 3. Actualizar tracking
                            tracking = self._alert_tracking.get(AlertEvent.ALERT_DRIVER_ABSENT, {})
                            if tracking:
                                tracking.update({
                                    'last_resolution_time': current_time,
                                    'last_resolution_method': 'auto_pause',
                                    'resolved_alert_id': recent_event.id,
                                    'total_repetitions': 3
                                })
                except Exception as db_e:
                    logging.error(f"[ALERT] Error actualizando alerta por auto-pausa: {db_e}")
            else:
                logging.warning(f"[SESSION] No se pudo pausar por ausencia: {msg}")
        except Exception as e:
            logging.error(f"[SESSION] Error al pausar por ausencia: {str(e)}", exc_info=True)
    
    def auto_pause_multiple_people(self) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Pausa la sesión automáticamente debido a múltiples personas detectadas.
        Versión pública para ser llamada desde el API.
        
        Returns:
            Tuple[bool, str, Dict]: (success, message, data)
        """
        try:
            ok, msg, pause_data = self.pause_session()
            if ok:
                current_time = timezone.now()
                self.paused_by_multiple_people = True
                logging.warning("[SESSION] Pausa automática por múltiples personas")
                
                # 1. Forzar desactivación inmediata en el motor
                try:
                    if hasattr(self, 'alert_engine') and self.alert_engine:
                        self.alert_engine.resolve_alert(AlertEvent.ALERT_MULTIPLE_PEOPLE)
                except Exception as engine_e:
                    logging.error(f"[ALERT-ENGINE] Error desactivando multiple_people: {engine_e}")

                # 2. Resolver alerta activa en BD
                try:
                    if self.camera_manager and self.camera_manager.session_id:
                        recent_event = AlertEvent.objects.filter(
                            session_id=self.camera_manager.session_id,
                            alert_type=AlertEvent.ALERT_MULTIPLE_PEOPLE,
                            resolved_at__isnull=True
                        ).order_by('-triggered_at').first()
                        
                        if recent_event:
                            # Marcar como resuelta con detalles
                            meta = recent_event.metadata or {}
                            meta.update({
                                'auto_paused_after_repetitions': True,
                                'repetition_limit_reached': True,
                                'resolved_by_auto_pause': True,
                                'resolution_time': current_time.isoformat(),
                                'total_duration_seconds': (current_time - recent_event.triggered_at).total_seconds()
                            })
                            recent_event.resolved_at = current_time
                            recent_event.resolution_method = 'auto_pause'
                            recent_event.metadata = meta
                            recent_event.save(update_fields=['resolved_at', 'resolution_method', 'metadata'])
                            
                            logging.info(f"[ALERT] ✓ Alerta {recent_event.id} resuelta por auto-pausa")
                            
                            # 3. Actualizar tracking
                            tracking = self._alert_tracking.get(AlertEvent.ALERT_MULTIPLE_PEOPLE, {})
                            if tracking:
                                tracking.update({
                                    'last_resolution_time': current_time,
                                    'last_resolution_method': 'auto_pause',
                                    'resolved_alert_id': recent_event.id
                                })
                except Exception as db_e:
                    logging.error(f"[ALERT] Error actualizando alerta por auto-pausa: {db_e}")
                
                return True, "Monitoreo pausado por múltiples personas", pause_data
            else:
                logging.warning(f"[SESSION] No se pudo pausar por múltiples personas: {msg}")
                return False, msg, {}
        except Exception as e:
            logging.error(f"[SESSION] Error al pausar por múltiples personas: {str(e)}", exc_info=True)
            return False, str(e), {}
    
    def _pause_session_due_to_multiple_people(self):
        """Pausa la sesión debido a 3 detecciones de múltiples personas.
        Debe pausar el procesamiento (cámara) y dejar trazabilidad de la causa.
        """
        try:
            ok, msg, _ = self.pause_session()
            if ok:
                current_time = timezone.now()
                self.paused_by_multiple_people = True
                logging.warning("[SESSION] Pausa automática por múltiples personas repetidas")
                
                # 1. Forzar desactivación inmediata en el motor
                try:
                    if hasattr(self, 'alert_engine') and self.alert_engine:
                        self.alert_engine.resolve_alert(AlertEvent.ALERT_MULTIPLE_PEOPLE)
                except Exception as engine_e:
                    logging.error(f"[ALERT-ENGINE] Error desactivando multiple_people: {engine_e}")

                # 2. Resolver alerta activa en BD
                try:
                    if self.camera_manager and self.camera_manager.session_id:
                        recent_event = AlertEvent.objects.filter(
                            session_id=self.camera_manager.session_id,
                            alert_type=AlertEvent.ALERT_MULTIPLE_PEOPLE,
                            resolved_at__isnull=True
                        ).order_by('-triggered_at').first()
                        
                        if recent_event:
                            # Marcar como resuelta con detalles
                            meta = recent_event.metadata or {}
                            meta.update({
                                'auto_paused_after_repetitions': True,
                                'repetition_limit_reached': True,
                                'repetition_count': 3,
                                'resolved_by_auto_pause': True,
                                'resolution_time': current_time.isoformat(),
                                'total_duration_seconds': (current_time - recent_event.triggered_at).total_seconds()
                            })
                            recent_event.resolved_at = current_time
                            recent_event.resolution_method = 'auto_pause'
                            recent_event.metadata = meta
                            recent_event.save(update_fields=['resolved_at', 'resolution_method', 'metadata'])
                            
                            # Resuelto por auto-pausa
                            
                            # 3. Actualizar tracking
                            tracking = self._alert_tracking.get(AlertEvent.ALERT_MULTIPLE_PEOPLE, {})
                            if tracking:
                                tracking.update({
                                    'last_resolution_time': current_time,
                                    'last_resolution_method': 'auto_pause',
                                    'resolved_alert_id': recent_event.id,
                                    'total_repetitions': 3
                                })
                except Exception as db_e:
                    logging.error(f"[ALERT] Error actualizando alerta por auto-pausa: {db_e}")
            else:
                logging.warning(f"[SESSION] No se pudo pausar por múltiples personas: {msg}")
        except Exception as e:
            logging.error(f"[SESSION] Error al pausar por múltiples personas: {str(e)}", exc_info=True)
    
    def _select_and_save_alert(self, alert_candidates: List[Dict[str, Any]], 
    current_time: float) -> List[Dict[str, Any]]:
        
        if not alert_candidates:
            return []
            
        # Mapeo de tipos de alerta a prioridad numérica
        PRIORITY_MAP = {
            AlertEvent.ALERT_MICROSLEEP: 1,
            AlertEvent.ALERT_FATIGUE: 1,
            AlertEvent.ALERT_LOW_BLINK_RATE: 2,
            AlertEvent.ALERT_HIGH_BLINK_RATE: 2,
            AlertEvent.ALERT_DRIVER_ABSENT: 2,
            AlertEvent.ALERT_MULTIPLE_PEOPLE: 2,
            AlertEvent.ALERT_FREQUENT_DISTRACT: 3,
            AlertEvent.ALERT_MICRO_RHYTHM: 3,
            AlertEvent.ALERT_CAMERA_OCCLUDED: 3,
            AlertEvent.ALERT_HEAD_TENSION: 4,
            AlertEvent.ALERT_BREAK_REMINDER: 99,  # Baja prioridad, no bloquea otras alertas
        }
        
        # Filtrar alertas por intervalo mínimo
        valid_alerts = []
        for alert in alert_candidates:
            alert_type = alert['type']
            last_time = self._last_alert_times.get(alert_type, 0)
            
            tracking = self._alert_tracking.get(alert_type, {})
            
            try:
                # Obtener configuración efectiva del usuario
                configured_cooldown = 60.0  # Default del modelo
                configured_repeat_interval = 5.0  # Default del modelo
                
                if self.camera_manager and self.camera_manager.session_id:
                    try:
                        session = MonitorSession.objects.select_related('user__monitoring_config').get(
                            id=self.camera_manager.session_id
                        )
                        user = session.user
                        if hasattr(user, 'monitoring_config') and user.monitoring_config:
                            configured_cooldown = float(getattr(user.monitoring_config, 'alert_cooldown_seconds', 60) or 60)
                            configured_repeat_interval = float(getattr(user.monitoring_config, 'alert_repeat_interval', 5) or 5)
                    except Exception as user_e:
                        logging.warning(f"[ALERT] No se pudo obtener configuración del usuario: {user_e}")
                
                current_reps = tracking.get('repetition_count', 0)
                
                # 🔥 BREAK REMINDER: Sin cooldown, se controla internamente en check_break_reminder
                if alert_type == AlertEvent.ALERT_BREAK_REMINDER:
                    cooldown = 0  # Sin cooldown adicional
                # Para alertas con AUTO-PAUSA (driver_absent, multiple_people)
                elif alert_type in [AlertEvent.ALERT_DRIVER_ABSENT, AlertEvent.ALERT_MULTIPLE_PEOPLE]:
                    if current_reps >= 1:
                        continue  # Ya sonó una vez, bloquear hasta que se resuelva
                    else:
                        cooldown = configured_repeat_interval
                elif alert_type == AlertEvent.ALERT_CAMERA_OCCLUDED:
                    cooldown = 999999  # Cooldown "infinito" - solo mostrar una vez hasta que se resuelva
                else:
                    cooldown = configured_cooldown
                
            except Exception as e:
                cooldown = 10.0
                logging.error(f"[ALERT] Config error {alert_type}: {e}")
            
            
            # Verificar si ha pasado suficiente tiempo
            last_time_unix = self._last_alert_times.get(alert_type, 0)
            
            # Si hay tracking con last_trigger_time (datetime), convertirlo a Unix timestamp
            tracking_time = tracking.get('last_trigger_time')
            if tracking_time:
                last_time_from_tracking = tracking_time.timestamp()
                last_time = max(last_time_unix, last_time_from_tracking)
            else:
                last_time = last_time_unix
            
            time_elapsed = current_time - last_time
            
            if time_elapsed >= cooldown:
                valid_alerts.append(alert)
        
        if not valid_alerts:
            return []
        
        # Separar break_reminder de otras alertas
        break_reminder_alert = None
        other_alerts = []
        
        for alert in valid_alerts:
            if alert['type'] == AlertEvent.ALERT_BREAK_REMINDER:
                break_reminder_alert = alert
            else:
                other_alerts.append(alert)
        
        # Seleccionar alerta normal por prioridad (si hay)
        selected_alerts = []
        
        if other_alerts:
            # Ordenar por prioridad las alertas normales
            sorted_alerts = sorted(
                other_alerts,
                key=lambda a: (PRIORITY_MAP.get(a['type'], 999), -float(a.get('timestamp', 0)))
            )
            selected_alerts.append(sorted_alerts[0])
            
            # Actualizar timestamp de última alerta normal
            alert_type = sorted_alerts[0]['type']
            self._last_alert_times[alert_type] = current_time
        
        # Agregar break_reminder si existe (se muestra junto con otras alertas y SÍ se guarda en BD)
        if break_reminder_alert:
            selected_alerts.append(break_reminder_alert)
            self._last_alert_times[AlertEvent.ALERT_BREAK_REMINDER] = current_time
        
        # Guardar en base de datos (incluyendo break_reminder)
        self._save_alerts_to_db(selected_alerts)
        
        return selected_alerts

    def _save_alerts_to_db(self, alerts: List[Dict[str, Any]]):
        """
        Guarda alertas en la base de datos manejando:
        1. Una sola alerta activa por tipo a la vez
        2. Conteo preciso considerando histéresis y resoluciones
        3. Intervalos de repetición configurados
        4. Estados de resolución automática
        """
        
        if not self.camera_manager or not self.camera_manager.session_id:
            return

        try:
            session = MonitorSession.objects.get(id=self.camera_manager.session_id)
            user = session.user
            
            for alert in alerts:
                alert_type = alert['type']
                current_time = timezone.now()
                
                # Obtener tracking para este tipo de alerta
                tracking = self._alert_tracking.setdefault(alert_type, {
                    'repetition_count': 0,
                    'last_trigger_time': None,
                    'last_alert_id': None,
                    'total_count': 0
                })
                
                # Verificar alerta activa existente
                existing_alert = AlertEvent.objects.filter(
                    session=session,
                    alert_type=alert_type,
                    resolved_at__isnull=True
                ).first()
                
                # Break Reminder: Solo permitir uno activo a la vez, no actualizar repeticiones
                if alert_type == AlertEvent.ALERT_BREAK_REMINDER:
                    if existing_alert:
                        # Ya hay un break reminder activo, no crear otro
                        continue
                    else:
                        # Crear nuevo break reminder
                        metadata = alert.get('metadata', {})
                        metadata.update({
                            'repetition_count': 0,
                            'total_alerts_today': tracking['total_count'] + 1
                        })
                        new_rep_count = 0
                        # Continuar al bloque de creación de AlertEvent
                
                elif existing_alert and alert_type in [AlertEvent.ALERT_DRIVER_ABSENT, AlertEvent.ALERT_MULTIPLE_PEOPLE, AlertEvent.ALERT_CAMERA_OCCLUDED]:
                    # Actualizar alerta existente para que "suene de nuevo"
                    if alert_type == AlertEvent.ALERT_DRIVER_ABSENT:
                        count = getattr(self, 'driver_absent_count', 0)
                    elif alert_type == AlertEvent.ALERT_MULTIPLE_PEOPLE:
                        count = getattr(self, 'multiple_people_count', 0)
                    else:  # camera_occluded
                        count = getattr(self, 'camera_occluded_count', 0)
                    
                    # Actualizar timestamp y metadata
                    existing_alert.timestamp = current_time
                    if existing_alert.metadata is None:
                        existing_alert.metadata = {}
                    existing_alert.metadata['repetition_count'] = count
                    existing_alert.metadata['last_sound_time'] = current_time.isoformat()
                    existing_alert.save(update_fields=['timestamp', 'metadata'])
                    
                    # Actualizar tracking
                    tracking.update({
                        'repetition_count': count,
                        'last_trigger_time': current_time,
                        'last_alert_id': existing_alert.id,
                        'total_count': tracking['total_count'] + 1
                    })
                    
                    # Verificar si alcanzamos el máximo de repeticiones para pausar
                    if alert_type == AlertEvent.ALERT_DRIVER_ABSENT and count >= 3:
                        self._pause_session_due_to_absence()
                    elif alert_type == AlertEvent.ALERT_MULTIPLE_PEOPLE and count >= 3:
                        self._pause_session_due_to_multiple_people()
                    
                    continue  # No crear nueva alerta
                elif existing_alert:
                    # Para otras alertas, no permitir duplicados
                    continue
                
                
                # Obtener configuración de repetición y metadata
                try:
                    if hasattr(user, 'monitoring_config') and user.monitoring_config:
                        repeat_interval = float(getattr(user.monitoring_config, 'alert_repeat_interval', 10) or 10)
                        repeat_max = int(getattr(user.monitoring_config, 'repeat_max_per_hour', 6) or 6)
                    else:
                        repeat_interval = 10.0
                        repeat_max = 6

                    try:
                        type_config = AlertTypeConfig.objects.get(alert_type=alert_type)
                        voice_clip = type_config.default_voice_clip.url if type_config.default_voice_clip else None
                        configured_description = type_config.description or ''
                    except AlertTypeConfig.DoesNotExist:
                        voice_clip = None
                        configured_description = ''
                except Exception as conf_e:
                    logging.error(f"[ALERT] Error obteniendo configuración: {conf_e}")
                    repeat_interval = 10.0
                    repeat_max = 6
                    voice_clip = None
                    configured_description = ''
                
                # Inicializar metadata
                if alert_type == AlertEvent.ALERT_BREAK_REMINDER:
                    # Ya se inicializó metadata arriba, no hacer nada
                    pass
                elif alert_type in [AlertEvent.ALERT_DRIVER_ABSENT, AlertEvent.ALERT_MULTIPLE_PEOPLE]:
                    try:
                        effective_cfg = {}
                        if hasattr(user, 'monitoring_config'):
                            from apps.monitoring.models import get_effective_detection_config as _get_eff
                            effective_cfg = _get_eff(user)
                        detection_delay = float(effective_cfg.get('detection_delay_seconds', 5.0))
                        hysteresis_timeout = float(effective_cfg.get('hysteresis_timeout_seconds', 30.0))
                        max_reps = 1
                    except Exception:
                        detection_delay = 5.0
                        hysteresis_timeout = 30.0
                        max_reps = 1

                    if alert_type == AlertEvent.ALERT_DRIVER_ABSENT:
                        count = getattr(self, 'driver_absent_count', 0)
                        first_detection = getattr(self, 'driver_absent_first_detection', None)
                    else:
                        count = getattr(self, 'multiple_people_count', 0)
                        first_detection = getattr(self, 'multiple_people_first_detection', None)

                    current_dt = timezone.now()
                    
                    if first_detection is None:
                        first_detection = current_dt
                        if alert_type == AlertEvent.ALERT_DRIVER_ABSENT:
                            self.driver_absent_first_detection = first_detection
                        else:
                            self.multiple_people_first_detection = first_detection

                    detection_time = (current_dt - first_detection).total_seconds()
                    
                    if detection_time >= detection_delay:
                        metadata = {
                            'repetition_count': count,
                            'total_alerts_today': tracking['total_count'] + 1,
                            'first_detection_time': first_detection.isoformat(),
                            'detection_delay': detection_delay,
                            'hysteresis_timeout': hysteresis_timeout,
                            'detection_time': detection_time
                        }
                        new_rep_count = count

                        if detection_time > hysteresis_timeout and count >= max_reps:
                            self.pause_session()
                            metadata['auto_paused'] = True
                    else:
                        continue
                elif alert_type == AlertEvent.ALERT_CAMERA_OCCLUDED:
                    try:
                        effective_cfg = {}
                        if hasattr(user, 'monitoring_config'):
                            from apps.monitoring.models import get_effective_detection_config as _get_eff
                            effective_cfg = _get_eff(user)
                        hysteresis_timeout = float(effective_cfg.get('hysteresis_timeout_seconds', 30.0))
                    except Exception:
                        hysteresis_timeout = 30.0

                    count = getattr(self, 'camera_occluded_count', 0)
                    first_detection = getattr(self, 'camera_occluded_first_detection', None)

                    current_dt = timezone.now()
                    detection_time = 0
                    if first_detection:
                        detection_time = (current_dt - first_detection).total_seconds()
                    
                    metadata = {
                        'repetition_count': count,
                        'total_alerts_today': tracking['total_count'] + 1,
                        'first_detection_time': first_detection.isoformat() if first_detection else current_dt.isoformat(),
                        'hysteresis_timeout': hysteresis_timeout,
                        'detection_time': detection_time,
                        'detection_delay': 0
                    }
                    metadata.update(alert.get('metadata', {}))
                    new_rep_count = count
                else:
                    # Para otras alertas
                    metadata = alert.get('metadata', {})
                    metadata.update({
                        'repetition_count': tracking['repetition_count'] + 1,
                        'total_alerts_today': tracking['total_count'] + 1
                    })
                    new_rep_count = tracking['repetition_count'] + 1
                
                # Verificar intervalo mínimo para alertas críticas
                if alert_type in [AlertEvent.ALERT_DRIVER_ABSENT, AlertEvent.ALERT_MULTIPLE_PEOPLE]:
                    if tracking['last_trigger_time']:
                        time_since_last = (current_time - tracking['last_trigger_time']).total_seconds()
                        
                        if time_since_last < repeat_interval:
                            continue
                
                # Verificar límite por hora (excepto break_reminder que se controla internamente)
                if alert_type != AlertEvent.ALERT_BREAK_REMINDER:
                    hourly_alerts = AlertEvent.objects.filter(
                        session=session,
                        alert_type=alert_type,
                        timestamp__gte=current_time - timezone.timedelta(hours=1)
                    ).count()
                    
                    if hourly_alerts >= repeat_max:
                        continue
                
                # Usar descripción del modelo AlertTypeConfig
                final_message = configured_description if configured_description else alert.get('message', '')
                
                # ✅ INCREMENTAR CONTADOR DE SESIÓN - cuenta CADA VEZ que aparece una alerta
                self.session_data['alert_count'] += 1
                
                # Buscar AlertEvent existente sin resolver
                existing_alert_second = AlertEvent.objects.filter(
                    session=session,
                    alert_type=alert_type,
                    resolved_at__isnull=True
                ).order_by('-triggered_at').first()
                
                if existing_alert_second:
                    # Reutilizar alerta existente
                    existing_alert_second.metadata = metadata
                    existing_alert_second.timestamp = current_time
                    if hasattr(existing_alert_second, 'last_updated'):
                        existing_alert_second.save(update_fields=['metadata', 'timestamp', 'last_updated'])
                    else:
                        existing_alert_second.save(update_fields=['metadata', 'timestamp'])
                    alert_event = existing_alert_second
                else:
                    # Crear nueva alerta
                    alert_event = AlertEvent.objects.create(
                        session=session,
                        alert_type=alert_type,
                        level=alert.get('level', 'medium'),
                        message=final_message,
                        voice_clip=type_config.default_voice_clip if 'type_config' in locals() and type_config and type_config.default_voice_clip else None,
                        timestamp=current_time,
                        metadata=metadata
                    )
                
                # Actualizar tracking
                tracking.update({
                    'repetition_count': new_rep_count,
                    'last_trigger_time': current_time,
                    'last_alert_id': alert_event.id,
                    'total_count': tracking['total_count'] + 1
                })
                
                # Actualizar contador de sesión en BD
                try:
                    session.alert_count = self.session_data['alert_count']
                    session.save(update_fields=['alert_count'])
                except Exception as save_e:
                    logging.error(f"[ALERT] Error actualizando alert_count en BD: {save_e}")

        except Exception as e:
            logging.error(f"[ALERT] Error al guardar alertas: {str(e)}")
            logging.exception(e)

    def check_alertas(self, metrics: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Verifica condiciones de las 10 alertas configuradas y retorna la de mayor prioridad.
        
        Sistema de prioridades y comportamientos:
        - 1 (CRITICAL):
          * microsleep: Requiere atención inmediata, ejercicios de reactivación
          * fatigue: Monitoreo EAR y parpadeo, ejercicios visuales
        
        - 2 (HIGH):
          * low_blink_rate: Monitoreo 30s/120s con EWMA
          * high_blink_rate: Similar pero umbral superior
          * driver_absent: 1 repetición, pausa si no se resuelve en tiempo configurable
          * multiple_people: 1 repetición, pausa si no se resuelve en tiempo configurable
        
        - 3 (MEDIUM):
          * frequent_distraction: Patrones de distracción, ejercicios de concentración
          * micro_rhythm: Detección temprana de somnolencia
          * camera_occluded: Sin límite de repeticiones, crítico para funcionamiento
        
        - 4 (LOW):
          * head_tension: Monitoreo postural y calibración de línea base
        
        Características especiales:
        - Histéresis configurable por tipo de alerta
        - Tiempos de detección ajustables (5-60s)
        - Pausado automático según configuración
        - Ejercicios asociados por tipo
        - Metadata detallada por cada tipo
        
        Retorna lista con máximo 1 alerta (la de mayor prioridad) o lista vacía.
        """
        # 🔥 IMPORTANTE: Si el monitoreo está pausado, NO generar nuevas alertas
        if self.camera_manager and self.camera_manager.is_paused:
            logging.debug("[ALERT] ⏸️ Monitoreo pausado - suprimiendo generación de alertas")
            return []
        
        current_time = time.time()
        
        if not isinstance(metrics, dict):
            logging.warning(f"[ALERT] metrics no es dict: {type(metrics)}")
            return []
        
        # Extraer datos de metrics
        faces_count = metrics.get('faces', metrics.get('faces_count', 0))
        multiple_faces = metrics.get('multiple_faces', False)
        eyes_detected = metrics.get('eyes_detected', False)
        eyes_closed = metrics.get('eyes_closed', False)
        occluded_flag = metrics.get('occluded', None)
        # Microsueño: aceptar ambas claves por compatibilidad ('microsleep_detected' o 'is_microsleep')
        microsleep_active = bool(
            metrics.get('microsleep_detected', metrics.get('is_microsleep', False))
        )
        avg_ear = metrics.get('ear', metrics.get('avg_ear', 1.0))  # CORREGIDO: 'ear' es el correcto
        blink_rate = metrics.get('blink_rate', 15.0)
        
        # 🔍 DEBUG: Log de métricas para diagnosticar detección de oclusión vs microsueño
        logging.info(f"[ALERT-DEBUG] faces={faces_count}, eyes_det={eyes_detected}, eyes_closed={eyes_closed}, "
                    f"occluded={occluded_flag}, EAR={avg_ear:.3f}, microsleep={microsleep_active}, blink_rate={blink_rate:.1f}")
        
        # Lista de alertas candidatas
        alert_candidates = []
        
        # Debug de estado global
        logging.info("[ALERT-STATE] Estado actual del sistema de alertas:")
        logging.info(f"  - Sesión pausada: {self.camera_manager.is_paused}")
        logging.info(f"  - Total alertas: {self.session_data.get('alert_count', 0)}")
        if hasattr(self, '_alert_tracking'):
            for alert_type, data in self._alert_tracking.items():
                logging.info(f"  - {alert_type}: rep={data.get('repetition_count', 0)}, "
                           f"última={data.get('last_trigger_time', 'nunca')}")
        
        # =====================================================================
        # 1. DRIVER ABSENT (Priority 2, histéresis 5s)
        # =====================================================================
        driver_absent_result = self.check_driver_absent_alert(faces_count, current_time)
        if driver_absent_result:
            count = driver_absent_result.get('metadata', {}).get('repetition_count', 1)
            current_count = getattr(self, 'driver_absent_count', 0) + 1
            logging.info(f"[ALERT-DEBUG] ✅ Driver absent detectada (repetición {current_count}/3)")
            alert_candidates.append(driver_absent_result)
            # Si driver_absent se activa, NO evaluar otras alertas (no hay usuario)
            # Retornar inmediatamente después de aplicar lógica de pausa
            if self._should_pause_on_driver_absent():
                logging.warning(f"[ALERT-PAUSE] 🚨 Auto-pausando por ausencia ({count} repeticiones)")
                self._pause_session_due_to_absence()
            return self._select_and_save_alert(alert_candidates, current_time)
        
        # =====================================================================
        # 2. MULTIPLE PEOPLE (Priority 2, histéresis 5s)
        # =====================================================================
        multiple_people_result = self.check_multiple_people_alert(
            faces_count, multiple_faces, current_time
        )
        if multiple_people_result:
            count = multiple_people_result.get('metadata', {}).get('repetition_count', 1)
            logging.info(f"[ALERT-DEBUG] ✅ Multiple people detectada (repetición {count}/3)")
            alert_candidates.append(multiple_people_result)
            # Si multiple_people se activa 3+ veces, pausar sesión
            if self._should_pause_on_multiple_people():
                logging.warning(f"[ALERT-PAUSE] 🚨 Auto-pausando por múltiples personas ({count} repeticiones)")
                self._pause_session_due_to_multiple_people()
            # NO evaluar otras alertas
            return self._select_and_save_alert(alert_candidates, current_time)
        
        # =====================================================================
        # 3. MICROSLEEP (Priority 1, sustain 5s)
        # =====================================================================
        # 🔥 CRÍTICO: Solo detectar microsueño si los ojos están CERRADOS naturalmente
        # NO si están obstruidos/tapados por un objeto
        # Verificar que:
        # 1. eyes_closed = True (ojos cerrados naturalmente)
        # 2. occluded = False (NO hay oclusión física)
        # 3. eyes_detected = True (los landmarks de los ojos se detectan)
        
        can_detect_microsleep = (
            bool(metrics.get('eyes_closed', False)) and  # Ojos cerrados
            not bool(occluded_flag) and  # NO obstruidos
            bool(eyes_detected)  # Landmarks detectados
        )
        
        microsleep_result = self.check_microsleep_alert(
            can_detect_microsleep, metrics.get('frames_closed', 0.0), current_time
        )
        if microsleep_result:
            alert_candidates.append(microsleep_result)
        
        # Camera Occluded
        camera_occluded_result = self.check_camera_occluded_alert(
            faces_count, eyes_detected, eyes_closed, 
            microsleep_active, occluded_flag, current_time
        )
        if camera_occluded_result:
            alert_candidates.append(camera_occluded_result)
        
        # Fatigue
        user_config = self._get_user_config()
        fatigue_result = self.check_fatigue_alert(
            avg_ear, blink_rate, microsleep_active, 
            user_config['fatigue_ear_threshold'], current_time
        )
        if fatigue_result:
            alert_candidates.append(fatigue_result)
        
        # Low Blink Rate
        low_blink_result = self.check_low_blink_rate_alert(current_time)
        if low_blink_result:
            alert_candidates.append(low_blink_result)
        
        # High Blink Rate
        high_blink_result = self.check_high_blink_rate_alert(current_time)
        if high_blink_result:
            alert_candidates.append(high_blink_result)
        
        # Frequent Distraction
        freq_distraction_result = self.check_frequent_distraction_alert(current_time)
        if freq_distraction_result:
            alert_candidates.append(freq_distraction_result)
        
        # Micro Rhythm
        micro_rhythm_result = self.check_micro_rhythm_alert(metrics, current_time)
        if micro_rhythm_result:
            alert_candidates.append(micro_rhythm_result)
        
        # Head Tension
        head_tension_result = self.check_head_tension_alert(current_time)
        if head_tension_result:
            alert_candidates.append(head_tension_result)
        
        # Break Reminder
        break_reminder_result = self.check_break_reminder()
        if break_reminder_result:
            alert_candidates.append(break_reminder_result)

        for alert in alert_candidates:
            if 'message' not in alert:
                try:
                    config = AlertTypeConfig.objects.filter(alert_type=alert['type']).first()
                    alert['message'] = config.description if config and config.description else alert['type']
                except Exception:
                    alert['message'] = alert['type']
        
        result = self._select_and_save_alert(alert_candidates, current_time)
        return result
    
    def get_metrics(self) -> Dict[str, Any]:
        """Obtiene las métricas actuales con caché y procesamiento de alertas"""
        current_time = time.time()

        # Verificar si podemos usar el caché
        if (current_time - self.metrics_cache_time < self.metrics_cache_duration and 
            self.metrics_cache):
            logging.debug(f'[CACHE] Usando cache (edad: {current_time - self.metrics_cache_time:.3f}s)')
            return self.metrics_cache

        with self.lock:
            if not self.camera_manager or not self.camera_manager.is_running:
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
                base_metrics = self.camera_manager.get_latest_metrics()

                if not isinstance(base_metrics, dict):
                    logging.error(f"[METRICS] base_metrics no es dict: {type(base_metrics)}")
                    base_metrics = {}

                base_metrics = self.sanitize_metrics_dict(base_metrics)

                # Pausa automática si hay un ejercicio activo asociado a alertas
                try:
                    if self.camera_manager.session_id:
                        session = MonitorSession.objects.select_related('user').get(id=self.camera_manager.session_id)
                        user = session.user
                        active_ex = self._get_active_mapped_exercise(user)
                        # Comprobar si hay una ventana de gracia activa para no auto-pausar
                        from datetime import timedelta
                        now_tz = timezone.now()
                        grace_active = (
                            self.exercise_resume_grace_until is not None and
                            now_tz < self.exercise_resume_grace_until
                        )
                        
                        # TIMEOUT: Si estamos pausados por ejercicio por más de 10 minutos, forzar reanudación
                        # (protección contra ejercicios que no se cerraron correctamente)
                        if self.paused_by_exercise and self._paused_by_exercise_timestamp:
                            from datetime import timedelta
                            time_paused = (timezone.now() - self._paused_by_exercise_timestamp).total_seconds()
                            if time_paused > 600:  # 10 minutos
                                logging.warning(f"[EXERCISE] ⏰ TIMEOUT: Pausado por ejercicio durante {time_paused:.0f}s > 10min. Forzando reanudación.")
                                ok, msg, _ = self.resume_session()
                                if ok:
                                    self.paused_by_exercise = False
                                    self._last_checked_exercise_id = None
                                    self._paused_by_exercise_timestamp = None
                                    logging.info(f"[EXERCISE] ✅ Reanudación forzada por timeout exitosa")
                                # No retornar aquí, continuar con la lógica normal
                        
                        # Solo pausar por ejercicio si la sesión sigue activa (no está siendo detenida)
                        if active_ex and not self.paused_by_exercise and not grace_active and session.end_time is None:
                            # Verificar que no estemos en proceso de detener la sesión
                            try:
                                latest_session = MonitorSession.objects.get(id=self.camera_manager.session_id)
                                if latest_session.end_time is not None:
                                    logging.info("[EXERCISE] Sesión está siendo detenida, ignorar pausa automática")
                                    return
                            except Exception:
                                pass
                                
                            logging.info(f"[EXERCISE] 🎯 Pausando monitoreo por ejercicio: {active_ex.exercise.title if active_ex.exercise else 'Sin título'}")
                            ok, msg, _ = self.pause_session()
                            if ok:
                                self.paused_by_exercise = True
                                self._last_checked_exercise_id = active_ex.id
                                self._paused_by_exercise_timestamp = timezone.now()
                                base_metrics['paused_reason'] = 'exercise'
                                base_metrics['paused_exercise'] = getattr(active_ex.exercise, 'title', 'Ejercicio')
                                logging.info(f"[EXERCISE] ✅ Monitoreo pausado exitosamente por ejercicio")
                            else:
                                logging.warning(f"[EXERCISE] ⚠️ No se pudo pausar: {msg}")
                        elif active_ex and grace_active:
                            # Respetar la ventana de gracia: no auto-pausar aunque detectemos ejercicio activo
                            remaining = (self.exercise_resume_grace_until - now_tz).total_seconds()
                            logging.info(f"[EXERCISE] ⏳ Grace activo {remaining:.1f}s, evitando auto-pausa por ejercicio activo")
                                
                        elif active_ex and self.paused_by_exercise and active_ex.id != self._last_checked_exercise_id:
                            # El ejercicio cambió (raro pero posible) -> actualizar
                            self._last_checked_exercise_id = active_ex.id
                            base_metrics['paused_reason'] = 'exercise'
                            base_metrics['paused_exercise'] = getattr(active_ex.exercise, 'title', 'Ejercicio')
                            logging.info(f"[EXERCISE] 🔄 Ejercicio cambió a: {active_ex.exercise.title if active_ex.exercise else 'Sin título'}")
                            
                        elif active_ex and self.paused_by_exercise:
                            # Ejercicio sigue activo y ya estamos pausados -> mantener estado
                            base_metrics['paused_reason'] = 'exercise'
                            base_metrics['paused_exercise'] = getattr(active_ex.exercise, 'title', 'Ejercicio')
                            
                        elif (not active_ex) and self.paused_by_exercise:
                            # Ya NO hay ejercicio activo pero estábamos pausados
                            # Solo limpiar flags internos y mantener pausa
                            logging.info(f"[EXERCISE] ℹ️ Ejercicio finalizado - mantener monitoreo pausado")
                            self._last_checked_exercise_id = None
                            self._paused_by_exercise_timestamp = None
                            
                            # No hacer nada más - el usuario debe reanudar manualmente
                        elif (not active_ex) and not self.paused_by_exercise and self.exercise_resume_grace_until is not None:
                            # Si no hay ejercicio y había una gracia configurada, limpiarla cuando expire
                            if now_tz >= self.exercise_resume_grace_until:
                                self.exercise_resume_grace_until = None
                            
                        
                        elif (not active_ex) and not self.paused_by_exercise:
                            # No hay ejercicio y no estamos pausados -> Estado normal
                            logging.debug(f"[EXERCISE] Estado normal: sin ejercicio activo, monitoreo corriendo")
                                
                except Exception as e:
                    logging.error(f"[EXERCISE] ❌ Error en evaluación de pausa por ejercicio: {e}", exc_info=True)

                # Acumular muestras y alimentar analizador avanzado
                if not self.camera_manager.is_paused:
                    avg_ear = base_metrics.get('avg_ear', 0.0)
                    focus = base_metrics.get('focus', 'No detectado')
                    faces = base_metrics.get('faces', base_metrics.get('faces_count', 0))
                    eyes_detected = base_metrics.get('eyes_detected', False)
                    brightness = base_metrics.get('brightness', 0.0)

                    if 0 <= brightness <= 255:
                        self.brightness_samples.append(float(brightness))

                    if faces >= 1 and eyes_detected and 0 < avg_ear <= 1.0:
                        self.ear_samples.append(float(avg_ear))
                        
                        focused_states = ['Atento', 'Concentrado', 'Enfocado']
                        distracted_states = ['Mirando a los lados', 'Mirando arriba', 'Mirando abajo', 'Distraído', 'Uso de celular', 'Múltiples personas']
                        
                        if focus in focused_states:
                            self.focus_samples.append(True)
                        elif focus in distracted_states:
                            self.focus_samples.append(False)
                        
                        self.metrics_sample_count += 1
                    
                    # Alimentar el analizador avanzado con métricas actuales
                    if self.metrics_analyzer:
                        try:
                            # Calcular focus_score numérico
                            if self.focus_samples:
                                focus_score = (sum(1 for f in self.focus_samples if f) / len(self.focus_samples)) * 100
                            else:
                                focus_score = 0.0
                            
                            # Calcular blink_rate
                            if self.camera_manager.session_id:
                                session = MonitorSession.objects.get(id=self.camera_manager.session_id)
                                duration_minutes = (timezone.now() - session.start_time).total_seconds() / 60
                                blink_rate = (self.camera_manager.blink_counter / duration_minutes) if duration_minutes > 0 else 0
                            else:
                                blink_rate = 0.0
                            
                            self.metrics_analyzer.add_metrics({
                                'avg_ear': avg_ear,
                                'blink_rate': blink_rate,
                                'focus_score': focus_score,
                                'head_yaw': base_metrics.get('head_yaw', 0.0),
                                'head_pitch': base_metrics.get('head_pitch', 0.0)
                            })
                        except Exception as e:
                            logging.error(f"[METRICS] Error alimentando analizador avanzado: {e}")

                # Limitar tamaño de arrays
                max_samples = 10000
                if len(self.ear_samples) > max_samples:
                    self.ear_samples = self.ear_samples[-5000:]
                if len(self.focus_samples) > max_samples:
                    self.focus_samples = self.focus_samples[-5000:]
                if len(self.brightness_samples) > max_samples:
                    self.brightness_samples = self.brightness_samples[-5000:]

                # Normalizar claves de rostro/ojos provenientes del detector
                faces_value = base_metrics.get('faces', None)
                faces_count_value = base_metrics.get('faces_count', None)
                try:
                    if faces_value is None and faces_count_value is None:
                        logging.debug(f"[METRICS-NORM] Sin 'faces' ni 'faces_count' en base_metrics: keys={list(base_metrics.keys())[:10]}")
                except Exception:
                    pass

                faces_normalized = 0
                if isinstance(faces_value, (int, float)):
                    faces_normalized = int(faces_value)
                elif isinstance(faces_count_value, (int, float)):
                    faces_normalized = int(faces_count_value)

                face_detected_flag = bool(base_metrics.get('face_detected', faces_normalized > 0))

                raw_metrics = {
                    'avg_ear': float(base_metrics.get('avg_ear', 0.0)),
                    'focus': str(base_metrics.get('focus', 'No detectado')),
                    'faces': int(faces_normalized),
                    'face_detected': bool(face_detected_flag),
                    'eyes_detected': bool(base_metrics.get('eyes_detected', False)),
                    'total_blinks': int(base_metrics.get('total_blinks', 0)),
                    'blink_count': int(base_metrics.get('total_blinks', 0)),
                    # Pose de cabeza y mirada (exponer ambas claves por compatibilidad)
                    'head_yaw': self.safe_json_value(base_metrics.get('head_yaw')),
                    'head_pitch': self.safe_json_value(base_metrics.get('head_pitch')),
                    'head_roll': self.safe_json_value(base_metrics.get('head_roll')),
                    'gaze_yaw': self.safe_json_value(base_metrics.get('gaze_yaw', base_metrics.get('head_yaw'))),
                    'gaze_pitch': self.safe_json_value(base_metrics.get('gaze_pitch', base_metrics.get('head_pitch'))),
                    'gaze_method': str(base_metrics.get('gaze_method', 'unknown')),
                    'yawn_confidence': float(base_metrics.get('yawn_confidence', 0.0)),
                    'phone_confidence': float(base_metrics.get('phone_confidence', 0.0)),
                    # Claves críticas adicionales para el sistema de alertas
                    'brightness': float(base_metrics.get('brightness', 255)),
                    'is_microsleep': bool(base_metrics.get('is_microsleep', base_metrics.get('microsleep_detected', False))),
                    'microsleep_detected': bool(base_metrics.get('microsleep_detected', base_metrics.get('is_microsleep', False))),
                    'frames_closed': float(base_metrics.get('microsleep_duration', base_metrics.get('frames_closed', 0.0))),
                    'eyes_closed': bool(base_metrics.get('eyes_closed', False)),
                    'occluded': base_metrics.get('occluded', None),
                    'multiple_faces': bool(base_metrics.get('multiple_faces', False)),
                }

                # Exponer motivo de pausa si aplica
                if self.paused_by_exercise:
                    raw_metrics['paused_reason'] = 'exercise'
                    raw_metrics['paused_exercise'] = base_metrics.get('paused_exercise')
                elif getattr(self, 'paused_by_absence', False):
                    raw_metrics['paused_reason'] = 'absence'
                elif getattr(self, 'paused_by_multiple_people', False):
                    raw_metrics['paused_reason'] = 'multiple_people'

                is_paused = self.camera_manager.is_paused

                # Verificar estado de la sesión
                if self.camera_manager.session_id:
                    try:
                        session = MonitorSession.objects.get(
                            id=self.camera_manager.session_id
                        )
                        if session.end_time:
                            # Si la sesión está finalizada, limpiar estados de ejercicio
                            self.paused_by_exercise = False
                            self._last_checked_exercise_id = None
                            self._paused_by_exercise_timestamp = None
                            self.exercise_resume_grace_until = None
                            return {
                                'status': 'ended',
                                'message': 'Sesión finalizada',
                                'metrics': raw_metrics,
                                'is_paused': False,
                                'alerts': []
                            }

                        # Calcular métricas de sesión
                        current_time_tz = timezone.now()
                        session_duration = (current_time_tz - session.start_time).total_seconds()
                        
                        # Sumar pausas completadas
                        pause_duration = sum(
                            (p.resume_time - p.pause_time).total_seconds()
                            for p in session.pauses.all()
                            if p.resume_time
                        )
                        
                        # Si hay una pausa activa (sin resume_time), agregar su duración hasta ahora
                        if self.camera_manager.is_paused:
                            active_pause = session.pauses.filter(resume_time__isnull=True).last()
                            if active_pause:
                                pause_duration += (current_time_tz - active_pause.pause_time).total_seconds()
                        
                        effective_duration = session_duration - pause_duration
                        
                        # Actualizar session_data con effective_duration para break_reminder
                        self.session_data['effective_duration'] = effective_duration

                        current_avg_ear = 0.0
                        current_focus = 0.0

                        if self.ear_samples:
                            current_avg_ear = float(sum(self.ear_samples) / len(self.ear_samples))

                        if self.focus_samples:
                            focused_count = sum(1 for is_focused in self.focus_samples if is_focused)
                            current_focus = float((focused_count / len(self.focus_samples)) * 100)

                        raw_metrics.update({
                            'session_duration': float(session_duration),
                            'effective_duration': float(effective_duration),
                            'blink_rate': float((self.camera_manager.blink_counter / effective_duration) if effective_duration > 0 else 0),
                            'alert_count': int(self.session_data['alert_count']),
                            'current_avg_ear': float(current_avg_ear),
                            'current_focus_percent': float(current_focus),
                            'samples_collected': int(len(self.ear_samples))
                        })
                        
                        # Agregar análisis avanzado si está disponible
                        if self.metrics_analyzer and effective_duration > 30:
                            try:
                                comprehensive_analysis = self.metrics_analyzer.get_comprehensive_analysis()
                                raw_metrics['advanced_analysis'] = {
                                    'fatigue': comprehensive_analysis['fatigue'],
                                    'drowsiness': comprehensive_analysis['drowsiness'],
                                    'distraction': comprehensive_analysis['distraction'],
                                    'session_quality': comprehensive_analysis['session_quality']
                                }
                            except Exception as e:
                                logging.error(f"[METRICS] Error en análisis avanzado: {e}")

                    except MonitorSession.DoesNotExist:
                        logging.error(f"[METRICS] Sesión {self.camera_manager.session_id} no encontrada")

                # =====================================================================
                # REGISTRO DE EVENTOS PARA VENTANAS DESLIZANTES
                # =====================================================================
                current_time = time.time()
                
                # 1. Registrar blinks detectados
                if raw_metrics.get('blink_detected', False):
                    self._register_blink(current_time)

                # 1.1 Exponer tasas de parpadeo de ventanas en métricas para decisiones más precisas
                try:
                    rates = self._get_blink_rates(current_time)
                    raw_metrics['blink_rate_short'] = float(rates.get('short_rate', 0.0))
                    raw_metrics['blink_rate_long'] = float(rates.get('long_rate', 0.0))
                    raw_metrics['blink_rate_ewma'] = float(rates.get('ewma_rate', 0.0))
                except Exception:
                    raw_metrics['blink_rate_short'] = raw_metrics.get('blink_rate', 0.0)
                    raw_metrics['blink_rate_long'] = raw_metrics.get('blink_rate', 0.0)
                    raw_metrics['blink_rate_ewma'] = raw_metrics.get('blink_rate', 0.0)
                
                # 2. Registrar pose de cabeza (cada frame para análisis de varianza)
                head_yaw = raw_metrics.get('head_yaw', 0.0)
                head_pitch = raw_metrics.get('head_pitch', 0.0)
                if isinstance(head_yaw, (int, float)) and isinstance(head_pitch, (int, float)):
                    self._register_head_pose(current_time, head_yaw, head_pitch)
                    
                    # Calibración de baseline durante primeros 15s
                    if not self.head_pose_baseline['calibrated']:
                        if self.session_data.get('effective_duration', 0) <= self.head_pose_calibration_window:
                            # Recolectar muestras frontales (±15° yaw, ±15° pitch)
                            if abs(head_yaw) <= 15.0 and abs(head_pitch) <= 15.0:
                                self.head_pose_calibration_samples.append((head_yaw, head_pitch))
                        else:
                            # Finalizar calibración
                            if len(self.head_pose_calibration_samples) >= 5:
                                yaws = [y for y, p in self.head_pose_calibration_samples]
                                pitches = [p for y, p in self.head_pose_calibration_samples]
                                self.head_pose_baseline['yaw'] = float(np.median(yaws))
                                self.head_pose_baseline['pitch'] = float(np.median(pitches))
                                self.head_pose_baseline['calibrated'] = True
                                logging.info(f"[CALIBRATION] Baseline head pose: yaw={self.head_pose_baseline['yaw']:.1f}°, pitch={self.head_pose_baseline['pitch']:.1f}°")
                            else:
                                # Usar defaults si no hay suficientes muestras frontales
                                self.head_pose_baseline['yaw'] = 0.0
                                self.head_pose_baseline['pitch'] = 0.0
                                self.head_pose_baseline['calibrated'] = True
                                logging.warning(f"[CALIBRATION] Baseline insuficiente, usando defaults (yaw=0, pitch=0)")
                
                # 3. Registrar eventos de distracción
                # Trackear cambios en focus_state para calcular duración
                focus_state = raw_metrics.get('focus_state', 'No detectado')
                distracted_states = ['Mirando a los lados', 'Mirando arriba', 'Mirando abajo', 'Distraído']
                
                # Inicializar tracking de distracción si no existe
                if not hasattr(self, '_distraction_start_time'):
                    self._distraction_start_time = None
                    self._was_distracted = False
                
                is_currently_distracted = focus_state in distracted_states
                
                # Detectar inicio de distracción
                if is_currently_distracted and not self._was_distracted:
                    self._distraction_start_time = current_time
                    self._was_distracted = True
                
                # Detectar fin de distracción y registrar evento
                elif not is_currently_distracted and self._was_distracted:
                    if self._distraction_start_time:
                        duration = current_time - self._distraction_start_time
                        # Solo registrar si duración está en rango 3-10 segundos
                        if 3.0 <= duration <= 10.0:
                            self._register_distraction(self._distraction_start_time, duration)
                    self._distraction_start_time = None
                    self._was_distracted = False

                # Obtener alertas nuevas del sistema de detección
                new_alerts = self.check_alertas(raw_metrics)
                
                # 🔥 NUEVO: Rastrear alertas recientemente resueltas para notificar al frontend
                recently_resolved = []
                if self.camera_manager and self.camera_manager.session_id:
                    try:
                        from apps.monitoring.models import AlertEvent
                        from datetime import timedelta
                        # Buscar alertas resueltas en los últimos 10 segundos
                        cutoff_time = timezone.now() - timedelta(seconds=10)
                        recent_resolved_alerts = AlertEvent.objects.filter(
                            session_id=self.camera_manager.session_id,
                            resolved_at__isnull=False,
                            resolved_at__gte=cutoff_time,
                            resolution_method='hysteresis'  # Solo las resueltas por histéresis
                        ).values_list('alert_type', 'id')
                        
                        for alert_type, alert_id in recent_resolved_alerts:
                            recently_resolved.append({
                                'type': alert_type,
                                'id': alert_id,
                                'action': 'close'
                            })
                        
                        if recently_resolved:
                            print(f"\n📤 [METRICS] Notificando {len(recently_resolved)} alertas resueltas al frontend\n")
                    except Exception as e:
                        logging.error(f"[METRICS] Error obteniendo alertas resueltas: {e}")
                
                # También obtener alertas activas desde la base de datos
                # IMPORTANTE: Solo incluir alertas NO resueltas
                active_alerts_from_db = []
                if self.camera_manager and self.camera_manager.session_id:
                    try:
                        from apps.monitoring.models import AlertEvent
                        # 🔥 CRÍTICO: Filtrar SOLO alertas sin resolver
                        active_db_alerts = AlertEvent.objects.filter(
                            session_id=self.camera_manager.session_id,
                            resolved_at__isnull=True  # Solo alertas activas
                        ).order_by('-triggered_at')[:5]
                        
                        for db_alert in active_db_alerts:
                            # 🔥 DOBLE VERIFICACIÓN: Asegurar que resolved_at sea NULL
                            if db_alert.resolved_at is None:
                                active_alerts_from_db.append({
                                    'type': db_alert.alert_type,
                                    'level': db_alert.level,
                                    'message': db_alert.message,
                                    'timestamp': db_alert.triggered_at.timestamp(),
                                    'metadata': db_alert.metadata or {},
                                    'id': db_alert.id
                                })
                    except Exception as e:
                        logging.error(f"[METRICS] Error obteniendo alertas activas: {e}")
                
                # Combinar alertas nuevas con alertas activas (evitar duplicados)
                combined_alerts = list(new_alerts)
                for db_alert in active_alerts_from_db:
                    # Solo agregar si no está ya en new_alerts
                    if not any(a.get('type') == db_alert['type'] for a in combined_alerts):
                        combined_alerts.append(db_alert)
                
                sanitized_alerts = []
                for alert in combined_alerts:
                    try:
                        # Agregar voice_clip desde AlertTypeConfig si no es break_reminder
                        if alert.get('type') != 'break_reminder':
                            try:
                                from apps.monitoring.models import AlertTypeConfig
                                type_config = AlertTypeConfig.objects.get(alert_type=alert.get('type'))
                                if type_config.default_voice_clip:
                                    alert['voice_clip'] = type_config.default_voice_clip.url
                                # Adjuntar descripción del tipo si existe
                                if type_config.description:
                                    alert['description'] = type_config.description
                            except AlertTypeConfig.DoesNotExist:
                                pass
                            except Exception as e:
                                logging.warning(f"[METRICS] Error obteniendo voice_clip para {alert.get('type')}: {e}")
                        
                        # Adjuntar ejercicio recomendado basado en AlertExerciseMapping
                        try:
                            from apps.monitoring.models import AlertExerciseMapping
                            mapping = AlertExerciseMapping.objects.get(alert_type=alert.get('type'), is_active=True)
                            if mapping and mapping.exercise:
                                duration_minutes = getattr(mapping.exercise, 'total_duration_minutes', None)
                                if callable(duration_minutes):
                                    duration_minutes = duration_minutes()
                                alert['exercise'] = {
                                    'id': mapping.exercise.id,
                                    'title': mapping.exercise.title,
                                    'description': mapping.exercise.description,
                                    'duration': duration_minutes or 0,
                                }
                        except AlertExerciseMapping.DoesNotExist:
                            # No hay ejercicio asociado: no adjuntar nada
                            pass
                        except Exception as e:
                            logging.warning(f"[METRICS] Error adjuntando ejercicio para {alert.get('type')}: {e}")
                        
                        sanitized_alert = self.sanitize_metrics_dict(alert)
                        sanitized_alerts.append(sanitized_alert)
                    except Exception as e:
                        logging.error(f"[METRICS] Error sanitizando alerta: {e}")

                # Construir respuesta
                response = {
                    'status': 'success',
                    'metrics': raw_metrics,
                    'is_paused': bool(is_paused),
                    'alerts': sanitized_alerts,
                    'resolved_alerts': recently_resolved,  # 🔥 NUEVO: Notificar alertas resueltas
                    'timestamp': float(time.time())
                }
                
                # Log para debug
                logging.debug(f'[METRICS-RESPONSE] is_paused={is_paused}, paused_by_exercise={self.paused_by_exercise}, camera.is_paused={self.camera_manager.is_paused}')

                # Señalar razón de pausa específica si aplica
                if bool(is_paused):
                    if self.paused_by_exercise:
                        response['paused_reason'] = 'exercise'
                    elif getattr(self, 'paused_by_absence', False):
                        response['paused_reason'] = 'absence'
                    elif getattr(self, 'paused_by_multiple_people', False):
                        response['paused_reason'] = 'multiple_people'

                if is_paused:
                    if self.paused_by_exercise:
                        response['message'] = 'Pausado por ejercicio'
                    elif getattr(self, 'paused_by_absence', False):
                        response['message'] = 'Pausado por usuario ausente'
                    elif getattr(self, 'paused_by_multiple_people', False):
                        response['message'] = 'Pausado por múltiples personas detectadas'
                    else:
                        response['message'] = 'Monitoreo en pausa'
                elif sanitized_alerts:
                    response['message'] = str(sanitized_alerts[0].get('message', ''))
                else:
                    response['message'] = 'Monitoreo activo'

                self.metrics_cache = response
                self.metrics_cache_time = time.time()

                return response

            except Exception as e:
                error_msg = f"Error al obtener métricas: {str(e)}"
                logging.error(f"[METRICS] {error_msg}", exc_info=True)

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


    def safe_json_value(self, obj):
        """Convierte un valor a un tipo serializable por JSON de forma segura."""
        if obj is None:
            return None
        if isinstance(obj, (np.integer, np.int64, np.int32, np.int16, np.int8)):
            return int(obj)
        if isinstance(obj, (np.floating, np.float64, np.float32, np.float16)):
            return float(obj)
        if isinstance(obj, (np.bool_, bool)):
            return bool(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, (int, float, str, type(None))):
            return obj
        try:
            # Intento final para otros tipos numéricos
            return float(obj)
        except (ValueError, TypeError):
            # Si todo falla, convertir a string
            return str(obj)

    def sanitize_metrics_dict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Recorre un diccionario y sanitiza todos sus valores para JSON."""
        if not isinstance(data, dict):
            return data
        sanitized_data = {}
        for k, v in data.items():
            if isinstance(v, dict):
                sanitized_data[k] = self.sanitize_metrics_dict(v)
            elif isinstance(v, (list, tuple)):
                sanitized_data[k] = [self.safe_json_value(item) for item in v]
            else:
                sanitized_data[k] = self.safe_json_value(v)
        return sanitized_data

    def _get_active_mapped_exercise(self, user):
        """Retorna la ExerciseSession activa para ejercicios mapeados a alertas, si existe."""
        try:
            from datetime import timedelta
            
            exercise_ids = list(
                AlertExerciseMapping.objects.filter(is_active=True, exercise__isnull=False)
                .values_list('exercise_id', flat=True)
            )
            if not exercise_ids:
                return None
            
            # Buscar sesiones que:
            # 1. No estén completadas (completed=False AND completed_at IS NULL)
            # 2. Y que se hayan iniciado en los últimos 5 minutos (ventana realista)
            recent_time = timezone.now() - timedelta(minutes=5)
            
            # Query para sesiones activas
            query = ExerciseSession.objects.filter(
                user=user,
                exercise_id__in=exercise_ids,
                started_at__gte=recent_time,
                completed=False,  # CRÍTICO: solo no completadas
                completed_at__isnull=True  # Y sin fecha de completado
            )
            
            # Log de todas las sesiones para debug
            all_recent = ExerciseSession.objects.filter(
                user=user,
                exercise_id__in=exercise_ids,
                started_at__gte=recent_time
            ).order_by('-started_at')
            
            if all_recent.exists():
                logging.debug(f"[EXERCISE] Sesiones recientes (últimos 5 min): {all_recent.count()}")
                for s in all_recent[:3]:
                    logging.debug(f"  - ID:{s.id} completed={s.completed} completed_at={s.completed_at} started={s.started_at}")
            
            active_session = query.order_by('-started_at').first()
            
            if active_session:
                logging.info(f"[EXERCISE] ✅ Sesión activa detectada: #{active_session.id} - {active_session.exercise.title if active_session.exercise else 'Sin título'} (started: {active_session.started_at})")
            else:
                logging.debug(f"[EXERCISE] ✓ No hay sesiones activas para el usuario")
            
            return active_session
        except Exception as e:
            logging.error(f"[EXERCISE] Error consultando sesiones activas: {e}", exc_info=True)
            return None

# Instancia global del controlador
controller = MonitoringController()