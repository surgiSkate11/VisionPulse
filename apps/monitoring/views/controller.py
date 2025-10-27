"""
Controller - Lógica de negocio y gestión de sesiones
Este módulo maneja el ciclo de vida completo de las sesiones de monitoreo
"""

import logging
import threading
import time
import json
import os
from typing import Dict, Any, Optional, Tuple, List

import cv2
import numpy as np
from django.utils import timezone

from ..models import MonitorSession, SessionPause, AlertEvent, get_effective_detection_config
from .camera import CameraManager, BlinkDetector


class MonitoringController:
    """Clase para manejar la lógica de negocio y las sesiones de monitoreo"""

    def __init__(self):
        self.camera_manager = None  # Se inicializará con la configuración del usuario en start_session
        self.lock = threading.Lock()
        self.session_lock = threading.Lock()
        self.metrics_cache = {}
        self.metrics_cache_time = 0
        self.metrics_cache_duration = 0.5  # 500ms de cache
        # Eliminamos cooldown y lista de alertas activas
        # self.active_alerts = []
        # self.last_alert_time = 0
        # self.alert_cooldown = 5.0

        # Añadimos diccionario de estados de alerta
        self.alert_states = {}

        # Acumuladores para métricas promedio
        self.ear_samples = []
        self.focus_samples = []
        self.head_yaw_samples = []
        self.head_pitch_samples = []
        self.head_roll_samples = []
        self.metrics_sample_count = 0
        
        # Tracking de bostezos para evitar duplicados
        self.last_yawn_count_seen = 0
        
        # Control de recordatorios de descanso
        self.last_break_reminder = 0
        self.break_reminder_interval = 20 * 60  # default: 20 minutos en segundos
        self.user_config = None  # Almacenar configuración del usuario
        
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
            # Guardar configuración del usuario
            self.user_config = user
            
            # Configurar recordatorios de descanso
            if hasattr(user, 'break_reminder_interval') and user.break_reminder_interval:
                self.break_reminder_interval = user.break_reminder_interval * 60  # convertir minutos a segundos
                logging.info(f"[SESSION] Recordatorios de descanso cada {user.break_reminder_interval} minutos")
            
            self.last_break_reminder = time.time()  # Resetear contador
            
            # Inicializar o reinicializar CameraManager con configuración efectiva
            try:
                effective_cfg = get_effective_detection_config(user)
            except Exception as cfg_e:
                logging.error(f"[SESSION] No se pudo construir config efectiva: {cfg_e}")
                effective_cfg = {}

            if self.camera_manager is None:
                logging.info(f"[SESSION] Inicializando CameraManager con configuración de {user.username}")
                self.camera_manager = CameraManager(user_config=user, effective_config=effective_cfg)
            elif self.camera_manager.is_running:
                logging.warning(f"[SESSION] Sesión ya activa. Usuario: {user.username}")
                return False, "Ya hay una sesión activa", None
            else:
                # Reinicializar el detector con la nueva configuración del usuario
                logging.info(f"[SESSION] Reinicializando detector con configuración de {user.username}")
                self.camera_manager.user_config = user
                self.camera_manager.blink_detector = BlinkDetector(user_config=user)
                try:
                    self.camera_manager.effective_config = effective_cfg
                except Exception:
                    pass
                
                # Actualizar intervalo de muestreo
                if hasattr(user, 'sampling_interval_seconds') and user.sampling_interval_seconds:
                    self.camera_manager.frame_interval = user.sampling_interval_seconds / 30.0
                
                # Actualizar frecuencia de análisis
                if hasattr(user, 'monitoring_frequency') and user.monitoring_frequency:
                    self.camera_manager.analysis_interval = user.monitoring_frequency

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

                # Guardar en metadata de la sesión
                try:
                    session.metadata = {
                        **(session.metadata or {}),
                        'effective_config': effective_cfg,
                    }
                    session.save(update_fields=['metadata'])
                except Exception as meta_e:
                    logging.debug(f"[SESSION] No se pudo guardar metadata de config: {meta_e}")

                # Exponer en camera_manager para posibles usos futuros
                try:
                    setattr(self.camera_manager, 'effective_config', effective_cfg)
                except Exception:
                    pass

                # Resetear acumuladores de métricas
                self.ear_samples = []
                self.focus_samples = []
                self.metrics_sample_count = 0

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
        # self.active_alerts.clear()  # Si ya no existe, eliminar
        # self.last_alert_time = 0     # Si ya no existe, eliminar
        self.metrics_cache.clear()
        self.metrics_cache_time = 0
        self.alert_states.clear() # Limpiar estados de alerta

        # Resetear acumuladores
        self.ear_samples = []
        self.focus_samples = []
        self.head_yaw_samples = []
        self.head_pitch_samples = []
        self.head_roll_samples = []
        self.metrics_sample_count = 0
        
        # Resetear contador de bostezos
        self.last_yawn_count_seen = 0
    
    def reload_user_config(self, user):
        """Recarga la configuración del usuario en tiempo real durante una sesión activa"""
        try:
            if self.camera_manager is None:
                logging.warning("[CONFIG] No hay CameraManager inicializado")
                return False, "No hay sesión activa"
            
            logging.info(f"[CONFIG] Recargando configuración de {user.username}")
            
            # Actualizar configuración en CameraManager
            self.camera_manager.user_config = user
            
            # Reinicializar detector con nueva configuración
            self.camera_manager.blink_detector = BlinkDetector(user_config=user)
            
            # Actualizar intervalo de muestreo
            if hasattr(user, 'sampling_interval_seconds') and user.sampling_interval_seconds:
                self.camera_manager.frame_interval = user.sampling_interval_seconds / 30.0
            
            # Actualizar cooldown de alertas basado en configuración
            if hasattr(user, 'monitoring_frequency') and user.monitoring_frequency:
                self.alert_cooldown = float(user.monitoring_frequency)
            
            logging.info(f"[CONFIG] Configuración actualizada: EAR={user.ear_threshold}, sensibilidad={user.face_detection_sensitivity}")
            return True, "Configuración actualizada correctamente"
            
        except Exception as e:
            logging.error(f"[CONFIG] Error al recargar configuración: {str(e)}")
            return False, f"Error: {str(e)}"
    
    def end_session(self) -> Tuple[bool, Optional[str], Dict[str, Any]]:
        """Finaliza la sesión actual y genera resumen de la sesión"""
        with self.session_lock:
            if not self.camera_manager or not self.camera_manager.is_running:
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

                        # CORREGIDO: Calcular promedios de métricas con validación
                        avg_ear = None
                        avg_focus = None
                        avg_head_yaw = None
                        avg_head_pitch = None
                        avg_head_roll = None

                        if self.ear_samples:
                            # Filtrar outliers extremos
                            valid_ear_samples = [e for e in self.ear_samples if 0 < e <= 1.0]
                            if valid_ear_samples:
                                avg_ear = sum(valid_ear_samples) / len(valid_ear_samples)
                                avg_ear = float(max(0.0, min(1.0, avg_ear)))

                        if self.focus_samples:
                            # Las muestras ahora son booleanas (True/False)
                            focused_count = sum(1 for is_focused in self.focus_samples if is_focused)
                            avg_focus = (focused_count / len(self.focus_samples)) * 100.0
                            avg_focus = float(max(0.0, min(100.0, avg_focus)))

                        # 🔥 NUEVO: Calcular métricas avanzadas del último snapshot
                        yawn_count = int(self.camera_manager.blink_detector.yawn_counter)
                        avg_mar = final_metrics.get('mar', 0.0)

                        # Si tenemos muestras acumuladas de head pose, promediarlas; si no, usar snapshot final
                        if self.head_yaw_samples:
                            try:
                                valid = [v for v in self.head_yaw_samples if isinstance(v, (int, float)) and abs(v) <= 90]
                                if valid:
                                    avg_head_yaw = sum(valid) / len(valid)
                            except Exception:
                                pass
                        if avg_head_yaw is None:
                            avg_head_yaw = final_metrics.get('head_yaw', 0.0)

                        if self.head_pitch_samples:
                            try:
                                valid = [v for v in self.head_pitch_samples if isinstance(v, (int, float)) and abs(v) <= 90]
                                if valid:
                                    avg_head_pitch = sum(valid) / len(valid)
                            except Exception:
                                pass
                        if avg_head_pitch is None:
                            avg_head_pitch = final_metrics.get('head_pitch', 0.0)

                        if self.head_roll_samples:
                            try:
                                valid = [v for v in self.head_roll_samples if isinstance(v, (int, float)) and abs(v) <= 180]
                                if valid:
                                    avg_head_roll = sum(valid) / len(valid)
                            except Exception:
                                pass
                        if avg_head_roll is None:
                            avg_head_roll = final_metrics.get('head_roll', 0.0)

                        head_pose_variance = final_metrics.get('head_pose_variance', 0.0)
                        avg_brightness = final_metrics.get('brightness', 0.0)
                        detection_rate = final_metrics.get('detection_rate', 0.0)

                        # Actualizar sesión con TODAS las métricas
                        session.end_time = end_time
                        session.total_blinks = self.camera_manager.blink_counter
                        session.total_yawns = yawn_count
                        session.total_duration = total_duration
                        session.effective_duration = effective_duration
                        session.pause_duration = pause_duration
                        session.total_alerts = self.session_data['alert_count']
                        session.avg_ear = avg_ear
                        session.focus_score = avg_focus
                        session.status = 'completed'
                        
                        # 🔥 NUEVO: Guardar métricas avanzadas
                        session.avg_mar = float(avg_mar) if avg_mar else None
                        session.avg_head_yaw = float(avg_head_yaw) if avg_head_yaw is not None else None
                        session.avg_head_pitch = float(avg_head_pitch) if avg_head_pitch is not None else None
                        session.avg_head_roll = float(avg_head_roll) if avg_head_roll is not None else None
                        session.head_pose_variance = float(head_pose_variance) if head_pose_variance else None
                        session.avg_brightness = float(avg_brightness) if avg_brightness else None
                        session.detection_rate = float(detection_rate) if detection_rate else None

                        # FIX: Formateo seguro de métricas finales
                        final_metrics_serializable = {
                            'avg_ear': float(avg_ear) if avg_ear is not None else None,
                            'focus_percent': float(avg_focus) if avg_focus is not None else None,
                            'total_blinks': int(self.camera_manager.blink_counter),
                            'total_alerts': int(self.session_data['alert_count']),
                            'ear_samples_count': len(self.ear_samples),
                            'focus_samples_count': len(self.focus_samples),
                            'yawn_count': int(self.camera_manager.blink_detector.yawn_counter),
                            # Convertir final_metrics a tipos serializables
                            'final_snapshot': {
                                k: (float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else v)
                                for k, v in final_metrics.items()
                                if k not in ['error', 'frame']
                            }
                        }

                        session.final_metrics = json.dumps(final_metrics_serializable)
                        session.save()

                        # Preparar resumen de la sesión
                        session_summary = {
                            'session_id': session.id,
                            'start_time': session.start_time.isoformat(),
                            'end_time': end_time.isoformat(),
                            'total_duration': float(total_duration),
                            'effective_duration': float(effective_duration),
                            'pause_duration': float(pause_duration),
                            'total_blinks': int(self.camera_manager.blink_counter),
                            'total_alerts': int(self.session_data['alert_count']),
                            'total_yawns': int(self.camera_manager.blink_detector.yawn_counter),
                            'avg_ear': float(avg_ear) if avg_ear is not None else 0.0,
                            'focus_percent': float(avg_focus) if avg_focus is not None else 0.0,
                            'avg_blink_rate': float(self.camera_manager.blink_counter / effective_duration) if effective_duration > 0 else 0.0,
                            'final_metrics': final_metrics
                        }

                        # FIX: Formateo seguro de logs
                        ear_str = f"{avg_ear:.3f}" if avg_ear is not None else "N/A"
                        focus_str = f"{avg_focus:.1f}" if avg_focus is not None else "N/A"
                        yawn_str = str(self.camera_manager.blink_detector.yawn_counter)

                        logging.info(f"[SESSION] Sesión {session.id} finalizada correctamente")
                        logging.info(f"[SESSION] Métricas: EAR={ear_str}, Focus={focus_str}%, Bostezos={yawn_str}")

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
                logging.exception(e)  # Log completo del traceback

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
            if not self.camera_manager or not self.camera_manager.is_running:
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
                    # Cargar imagen de pausa ANTES de establecer is_paused
                    import cv2
                    from django.conf import settings
                    pause_image_path = os.path.join(settings.BASE_DIR, 'static', 'img', 'iconos', 'pausa.png')
                    
                    # Determinar dimensiones del video
                    h, w = 480, 640  # Dimensiones por defecto
                    if self.camera_manager.video and self.camera_manager.video.isOpened():
                        w = int(self.camera_manager.video.get(cv2.CAP_PROP_FRAME_WIDTH))
                        h = int(self.camera_manager.video.get(cv2.CAP_PROP_FRAME_HEIGHT))
                    
                    pause_frame_loaded = False
                    
                    if os.path.exists(pause_image_path):
                        pause_image = cv2.imread(pause_image_path)
                        if pause_image is not None:
                            # Redimensionar la imagen de pausa al tamaño del video
                            pause_image_resized = cv2.resize(pause_image, (w, h), interpolation=cv2.INTER_AREA)
                            
                            # Agregar texto informativo sobre la imagen
                            font = cv2.FONT_HERSHEY_SIMPLEX
                            font_scale = 1.5
                            font_thickness = 3
                            
                            # Texto "SESIÓN EN PAUSA"
                            text = "SESION EN PAUSA"
                            text_size = cv2.getTextSize(text, font, font_scale, font_thickness)[0]
                            text_x = (w - text_size[0]) // 2
                            text_y = h // 2
                            
                            # Fondo semi-transparente para el texto
                            overlay = pause_image_resized.copy()
                            cv2.rectangle(overlay, 
                                        (text_x - 30, text_y - text_size[1] - 30),
                                        (text_x + text_size[0] + 30, text_y + 30),
                                        (0, 0, 0), -1)
                            
                            # Mezclar el fondo con transparencia
                            alpha = 0.7
                            pause_image_resized = cv2.addWeighted(overlay, alpha, pause_image_resized, 1 - alpha, 0)
                            
                            # Agregar texto en blanco
                            cv2.putText(pause_image_resized, text, 
                                      (text_x, text_y), 
                                      font, font_scale, (255, 255, 255), font_thickness, cv2.LINE_AA)
                            
                            # Texto secundario
                            sub_text = "Presiona 'Reanudar' para continuar"
                            sub_font_scale = 0.8
                            sub_text_size = cv2.getTextSize(sub_text, font, sub_font_scale, 2)[0]
                            sub_text_x = (w - sub_text_size[0]) // 2
                            sub_text_y = text_y + 60
                            
                            cv2.putText(pause_image_resized, sub_text,
                                      (sub_text_x, sub_text_y),
                                      font, sub_font_scale, (200, 200, 200), 2, cv2.LINE_AA)
                            
                            self.camera_manager.pause_frame = pause_image_resized
                            pause_frame_loaded = True
                            logging.info(f"[PAUSE] Imagen de pausa cargada correctamente: {pause_image_path}")
                        else:
                            logging.warning("[PAUSE] No se pudo leer la imagen de pausa (imread retornó None)")
                    else:
                        logging.warning(f"[PAUSE] Imagen de pausa no encontrada en: {pause_image_path}")
                    
                    # Si no se pudo cargar la imagen, crear una imagen negra con texto
                    if not pause_frame_loaded:
                        pause_image_resized = np.zeros((h, w, 3), dtype=np.uint8)
                        font = cv2.FONT_HERSHEY_SIMPLEX
                        text = "SESION EN PAUSA"
                        font_scale = 1.5
                        font_thickness = 3
                        text_size = cv2.getTextSize(text, font, font_scale, font_thickness)[0]
                        text_x = (w - text_size[0]) // 2
                        text_y = h // 2
                        cv2.putText(pause_image_resized, text, (text_x, text_y), 
                                   font, font_scale, (255, 255, 255), font_thickness, cv2.LINE_AA)
                        
                        sub_text = "Presiona 'Reanudar' para continuar"
                        sub_font_scale = 0.8
                        sub_text_size = cv2.getTextSize(sub_text, font, sub_font_scale, 2)[0]
                        sub_text_x = (w - sub_text_size[0]) // 2
                        sub_text_y = text_y + 60
                        cv2.putText(pause_image_resized, sub_text, (sub_text_x, sub_text_y),
                                   font, sub_font_scale, (200, 200, 200), 2, cv2.LINE_AA)
                        
                        self.camera_manager.pause_frame = pause_image_resized
                        logging.info("[PAUSE] Creada imagen de pausa negra con texto")
                    
                    # AHORA establecer is_paused para que get_frame() retorne pause_frame
                    self.camera_manager.is_paused = True
                    self.camera_manager.pause_metrics = {'status': 'paused', 'message': 'Sesión en pausa'}
                    
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
            if not self.camera_manager or not self.camera_manager.is_running:
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
    
    def check_break_reminder(self) -> Optional[Dict[str, Any]]:
        """Verifica si es momento de recordar un descanso al usuario"""
        if not self.user_config:
            return None
        
        current_time = time.time()
        time_since_last_break = current_time - self.last_break_reminder
        
        if time_since_last_break >= self.break_reminder_interval:
            self.last_break_reminder = current_time
            
            # Calcular tiempo de trabajo continuo
            minutes_worked = int(time_since_last_break / 60)
            
            logging.info(f"[BREAK] Recordatorio de descanso activado después de {minutes_worked} minutos")
            
            return {
                'type': 'break_reminder',
                'level': 'info',
                'message': f'¡Hora de descansar! Has trabajado {minutes_worked} minutos continuos',
                'timestamp': current_time,
                'minutes_worked': minutes_worked,
                'recommended_break_duration': 5  # 5 minutos de descanso recomendado
            }
        
        return None
    
    # ============================================================================
    # NUEVOS MÉTODOS AUXILIARES
    # ============================================================================
    def _get_user_config(self) -> Dict[str, Any]:
        """Obtiene configuración del usuario de forma segura"""
        try:
            if self.camera_manager and self.camera_manager.session_id:
                session = MonitorSession.objects.select_related('user').get(
                    id=self.camera_manager.session_id
                )
                user = session.user

                return {
                    'fatigue_ear_threshold': user.ear_threshold * user.fatigue_threshold,
                    'low_blink_rate_threshold': user.low_blink_rate_threshold,
                    'high_blink_rate_threshold': user.high_blink_rate_threshold,
                    'low_light_threshold': user.low_light_threshold
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

    def _save_alerts_to_db(self, alerts: List[Dict[str, Any]]):
        """Guarda alertas en la base de datos de forma segura"""
        if not self.camera_manager or not self.camera_manager.session_id:
            return

        try:
            session = MonitorSession.objects.get(id=self.camera_manager.session_id)
            saved_count = 0

            for alert in alerts:
                # No guardar break reminders
                if alert.get('type') == 'break_reminder':
                    continue

                AlertEvent.objects.create(
                    session=session,
                    alert_type=alert['type'],
                    level=alert['level'],
                    message=alert['message'],
                    timestamp=timezone.now(),
                    metadata=alert.get('metadata', {})
                )
                saved_count += 1

            if saved_count > 0:
                logging.info(f"[ALERT] {saved_count} alertas guardadas en BD")

        except Exception as e:
            logging.error(f"[ALERT] Error al guardar alertas: {str(e)}")

    def check_alertas(self, metrics: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        CORREGIDO: Validación estricta + cooldown selectivo por tipo de alerta
        """
        current_time = time.time()
        new_alerts = []

        # Recordatorio de descanso
        break_reminder = self.check_break_reminder()
        if break_reminder:
            new_alerts.append(break_reminder)

        faces_count = metrics.get('faces', 0)
        eyes_detected = metrics.get('eyes_detected', False)

        # Estado de ausencia
        if faces_count == 0:
            if not self.alert_states.get(AlertEvent.ALERT_DRIVER_ABSENT, False):
                new_alerts.append({
                    'type': AlertEvent.ALERT_DRIVER_ABSENT,
                    'level': 'high',
                    'message': 'No se detecta ninguna persona frente a la cámara',
                    'timestamp': current_time,
                    'metadata': {'faces': faces_count}
                })
                self.alert_states[AlertEvent.ALERT_DRIVER_ABSENT] = True
            self.alert_states[AlertEvent.ALERT_MULTIPLE_PEOPLE] = False
            self.alert_states[AlertEvent.ALERT_DISTRACT] = False
            self.alert_states[AlertEvent.ALERT_PHONE_USE] = False
            self._save_alerts_to_db(new_alerts)
            return new_alerts
        else:
            self.alert_states[AlertEvent.ALERT_DRIVER_ABSENT] = False

        # Estado de múltiples personas
        if faces_count > 1:
            if not self.alert_states.get(AlertEvent.ALERT_MULTIPLE_PEOPLE, False):
                new_alerts.append({
                    'type': AlertEvent.ALERT_MULTIPLE_PEOPLE,
                    'level': 'high',
                    'message': f'Se detectaron {faces_count} personas. Solo debe haber una',
                    'timestamp': current_time,
                    'metadata': {'faces': faces_count}
                })
                self.alert_states[AlertEvent.ALERT_MULTIPLE_PEOPLE] = True
            self._save_alerts_to_db(new_alerts)
            return new_alerts
        else:
            self.alert_states[AlertEvent.ALERT_MULTIPLE_PEOPLE] = False

        # Estado de cámara obstruida
        if faces_count > 0 and not eyes_detected:
            if not self.alert_states.get(AlertEvent.ALERT_CAMERA_OCCLUDED, False):
                new_alerts.append({
                    'type': AlertEvent.ALERT_CAMERA_OCCLUDED,
                    'level': 'medium',
                    'message': 'Cámara parcialmente obstruida. Se detecta rostro pero no los ojos',
                    'timestamp': current_time,
                    'metadata': {'faces': faces_count, 'eyes_detected': False}
                })
                self.alert_states[AlertEvent.ALERT_CAMERA_OCCLUDED] = True
            self._save_alerts_to_db(new_alerts)
            return new_alerts
        else:
            self.alert_states[AlertEvent.ALERT_CAMERA_OCCLUDED] = False

        # === A PARTIR DE AQUÍ: Solo si hay 1 cara Y ojos detectados ===

        try:
            # Obtener configuración del usuario
            user_config = self._get_user_config()

            # === ALERTAS BASADAS EN EAR (con cooldown) ===
            avg_ear = metrics.get('avg_ear', 1.0)

            if 0 < avg_ear <= 1.0 and not cooldown_active:
                # Fatiga visual
                if avg_ear < user_config['fatigue_ear_threshold']:
                    new_alerts.append({
                        'type': AlertEvent.ALERT_FATIGUE,
                        'level': 'high',
                        'message': f'Fatiga visual detectada (EAR: {avg_ear:.3f})',
                        'timestamp': current_time,
                        'metadata': {'ear': avg_ear, 'threshold': user_config['fatigue_ear_threshold']}
                    })

                # Microsueño
                if metrics.get('is_microsleep', False):
                    duration = metrics.get('microsleep_duration', 0)
                    new_alerts.append({
                        'type': AlertEvent.ALERT_MICROSLEEP,
                        'level': 'critical',
                        'message': f'¡Microsueño detectado! Ojos cerrados {duration:.1f}s',
                        'timestamp': current_time,
                        'metadata': {'duration_seconds': duration}
                    })

            # === ALERTAS BASADAS EN HEAD POSE (con cooldown) ===
            focus_state = metrics.get('focus', 'No detectado')
            head_yaw = metrics.get('head_yaw', 0.0)
            head_pitch = metrics.get('head_pitch', 0.0)

            if abs(head_yaw) < 90 and abs(head_pitch) < 90 and not cooldown_active:
                # Lista de estados de distracción REALES
                distracted_states = ['Mirando a los lados', 'Mirando arriba', 'Distraído']
                
                if focus_state in distracted_states:
                    new_alerts.append({
                        'type': AlertEvent.ALERT_DISTRACT,
                        'level': 'medium',
                        'message': f'Distracción: {focus_state}',
                        'timestamp': current_time,
                        'metadata': {'focus_state': focus_state, 'yaw': head_yaw, 'pitch': head_pitch}
                    })

                # Uso de celular (específico y más estricto)
                if focus_state == 'Uso de celular' and abs(head_pitch) > 30:
                    new_alerts.append({
                        'type': AlertEvent.ALERT_PHONE_USE,
                        'level': 'high',
                        'message': 'Posible uso de celular detectado',
                        'timestamp': current_time,
                        'metadata': {'yaw': head_yaw, 'pitch': head_pitch}
                    })

                # Estabilidad de pose (solo si hay suficientes datos)
                head_pose_stability = metrics.get('head_pose_stability', 'insufficient_data')

                if head_pose_stability == 'rigid':
                    variance = metrics.get('head_pose_variance', 0)
                    new_alerts.append({
                        'type': AlertEvent.ALERT_POSTURAL_RIGIDITY,
                        'level': 'low',
                        'message': f'Rigidez postural detectada',
                        'timestamp': current_time,
                        'metadata': {'variance': variance}
                    })

                elif head_pose_stability == 'agitated':
                    variance = metrics.get('head_pose_variance', 0)
                    new_alerts.append({
                        'type': AlertEvent.ALERT_HEAD_AGITATION,
                        'level': 'low',
                        'message': f'Movimiento excesivo de cabeza',
                        'timestamp': current_time,
                        'metadata': {'variance': variance}
                    })

            # === 🔥 ALERTAS DE BOSTEZOS - SIN COOLDOWN ===
            current_yawn_count = int(metrics.get('yawn_count', 0))
            
            # Solo procesar si hay NUEVOS bostezos desde la última verificación
            if current_yawn_count > self.last_yawn_count_seen:
                new_yawns = current_yawn_count - self.last_yawn_count_seen
                
                # Crear alerta por los nuevos bostezos
                mar = metrics.get('mar', 0.0)
                yawn_duration = metrics.get('yawn_duration', 0)
                
                new_alerts.append({
                    'type': AlertEvent.ALERT_YAWN,
                    'level': 'medium',
                    'message': f'Bostezo detectado ({new_yawns} nuevo(s))',
                    'timestamp': current_time,
                    'metadata': {
                        'mar': mar,
                        'duration': yawn_duration,
                        'total_yawns': current_yawn_count,
                        'new_yawns': new_yawns
                    }
                })
                
                # Actualizar contador
                self.last_yawn_count_seen = current_yawn_count
                
                logging.info(f"[YAWN] Detectados {new_yawns} bostezo(s) nuevo(s). Total: {current_yawn_count}")

            # === ALERTAS BASADAS EN BRILLO (con cooldown bajo) ===
            brightness = metrics.get('brightness', 255)
            if brightness < user_config['low_light_threshold'] and not cooldown_active:
                new_alerts.append({
                    'type': AlertEvent.ALERT_LOW_LIGHT,
                    'level': 'low',
                    'message': f'Iluminación baja (brillo: {brightness:.0f}/255)',
                    'timestamp': current_time,
                    'metadata': {'brightness': brightness, 'threshold': user_config['low_light_threshold']}
                })

            # === ALERTAS BASADAS EN TASA DE PARPADEO (con cooldown) ===
            # Solo después de 2 minutos de sesión
            if self.session_data.get('effective_duration', 0) > 120 and not cooldown_active:
                effective_duration_minutes = self.session_data['effective_duration'] / 60
                blink_rate = self.camera_manager.blink_counter / effective_duration_minutes

                # Tasa baja
                if blink_rate < user_config['low_blink_rate_threshold']:
                    new_alerts.append({
                        'type': AlertEvent.ALERT_LOW_BLINK_RATE,
                        'level': 'low',
                        'message': f'Tasa de parpadeo baja: {blink_rate:.1f}/min',
                        'timestamp': current_time,
                        'metadata': {'blink_rate': blink_rate, 'threshold': user_config['low_blink_rate_threshold']}
                    })

                # Tasa alta
                elif blink_rate > user_config['high_blink_rate_threshold']:
                    new_alerts.append({
                        'type': AlertEvent.ALERT_HIGH_BLINK_RATE,
                        'level': 'low',
                        'message': f'Tasa de parpadeo alta: {blink_rate:.1f}/min',
                        'timestamp': current_time,
                        'metadata': {'blink_rate': blink_rate, 'threshold': user_config['high_blink_rate_threshold']}
                    })

            # === GUARDAR ALERTAS Y ACTUALIZAR ESTADO ===
            non_break_alerts = [a for a in new_alerts if a.get('type') != 'break_reminder']

            if non_break_alerts:
                # Solo actualizar cooldown si NO son bostezos
                non_yawn_alerts = [a for a in non_break_alerts if a.get('type') != AlertEvent.ALERT_YAWN]
                if non_yawn_alerts:
                    self.last_alert_time = current_time
                
                self.session_data['alert_count'] += len(non_break_alerts)
                self._save_alerts_to_db(non_break_alerts)

                # Log para debugging
                for alert in non_break_alerts:
                    logging.info(f"[ALERT] {alert['type']}: {alert['message']}")

            return new_alerts

        except Exception as e:
            logging.error(f"[ALERT] Error al procesar alertas: {str(e)}")
            return new_alerts
    
    def get_metrics(self) -> Dict[str, Any]:
        """Obtiene las métricas actuales con caché y procesamiento de alertas"""
        current_time = time.time()
        
        # Verificar si podemos usar el caché
        if (current_time - self.metrics_cache_time < self.metrics_cache_duration and 
            self.metrics_cache):
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
                # Obtener métricas básicas
                base_metrics = self.camera_manager.get_latest_metrics()
                
                # Acumular muestras SOLO cuando hay detección válida
                if not self.camera_manager.is_paused:
                    avg_ear = base_metrics.get('avg_ear', 0.0)
                    focus = base_metrics.get('focus', 'No detectado')
                    faces = base_metrics.get('faces', 0)
                    eyes_detected = base_metrics.get('eyes_detected', False)
                    
                # IMPORTANTE: Solo acumular si hay cara Y ojos detectados
                if faces == 1 and eyes_detected and avg_ear > 0:
                    self.ear_samples.append(avg_ear)

                    # --- Lógica de Enfoque Simplificada ---
                    # Confiar en el string 'focus' que viene de camera.py
                    distracted_states = ['Mirando a los lados', 'Mirando arriba', 'Distraído', 'Uso de celular']
                    neutral_states = ['No detectado', 'Múltiples personas']

                    if focus == 'Atento':
                        self.focus_samples.append(True)
                        self.metrics_sample_count += 1
                    elif focus in distracted_states:
                        self.focus_samples.append(False)
                        self.metrics_sample_count += 1
                    # Si es neutral, no añadir muestra

                    # Acumular muestras de pose de cabeza si son válidas
                    head_yaw = base_metrics.get('head_yaw', 0.0)
                    head_pitch = base_metrics.get('head_pitch', 0.0)
                    head_roll = base_metrics.get('head_roll')
                    try:
                        if isinstance(head_yaw, (int, float)) and abs(head_yaw) <= 90:
                            self.head_yaw_samples.append(float(head_yaw))
                        if isinstance(head_pitch, (int, float)) and abs(head_pitch) <= 90:
                            self.head_pitch_samples.append(float(head_pitch))
                        if isinstance(head_roll, (int, float)) and abs(head_roll) <= 180:
                            self.head_roll_samples.append(float(head_roll))
                    except Exception:
                        pass
                    
                    # Limitar tamaño para evitar crecimiento infinito
                    if len(self.ear_samples) > 10000:
                        self.ear_samples = self.ear_samples[-5000:]
                    if len(self.focus_samples) > 10000:
                        self.focus_samples = self.focus_samples[-5000:]
                    if len(self.head_yaw_samples) > 10000:
                        self.head_yaw_samples = self.head_yaw_samples[-5000:]
                    if len(self.head_pitch_samples) > 10000:
                        self.head_pitch_samples = self.head_pitch_samples[-5000:]
                    if len(self.head_roll_samples) > 10000:
                        self.head_roll_samples = self.head_roll_samples[-5000:]

                    # 🔎 DEBUG: Log cada 30 muestras para auditar acumulación de enfoque
                    if logging.getLogger().isEnabledFor(logging.DEBUG) and (self.metrics_sample_count % 30 == 0):
                        try:
                            focused_count = sum(1 for f in self.focus_samples if f)
                            focus_percent = (focused_count / len(self.focus_samples)) * 100 if self.focus_samples else 0
                            logging.debug(
                                f"[FOCUS] muestras={len(self.focus_samples)}, enfocado={focused_count}, porcentaje={focus_percent:.1f}%, estado_actual={focus}"
                            )
                        except Exception:
                            pass
                
                raw_metrics = {
                    'avg_ear': base_metrics.get('avg_ear', 0.0),
                    'focus': base_metrics.get('focus', 'No detectado'),
                    'faces': base_metrics.get('faces', 0),
                    'eyes_detected': base_metrics.get('eyes_detected', False),
                    'total_blinks': base_metrics.get('total_blinks', 0),  # Consistente
                    'blink_count': base_metrics.get('total_blinks', 0),   # Alias para retrocompatibilidad
                    'yawn_count': base_metrics.get('yawn_count', 0),
                    'total_yawns': base_metrics.get('yawn_count', 0),
                    'is_yawning': base_metrics.get('is_yawning', False),
                    'mar': base_metrics.get('mar', 0.0),
                    # 🔥 Enhanced metrics (si disponibles)
                    'gaze_yaw': base_metrics.get('gaze_yaw'),
                    'gaze_pitch': base_metrics.get('gaze_pitch'),
                    'yawn_confidence': base_metrics.get('yawn_confidence', 0.0),
                    'is_using_phone': base_metrics.get('is_using_phone', False),
                    'phone_confidence': base_metrics.get('phone_confidence', 0.0),
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
                        
                        # CORREGIDO: Calcular promedios solo con muestras válidas
                        current_avg_ear = 0.0
                        current_focus = 0.0
                        
                        if self.ear_samples:
                            current_avg_ear = sum(self.ear_samples) / len(self.ear_samples)
                        
                        if self.focus_samples:
                            # Porcentaje de muestras donde is_focused es True
                            focused_count = sum(1 for is_focused in self.focus_samples if is_focused)
                            current_focus = (focused_count / len(self.focus_samples)) * 100
                        
                        # Agregar métricas calculadas
                        raw_metrics.update({
                            'session_duration': session_duration,
                            'effective_duration': effective_duration,
                            'blink_rate': (self.camera_manager.blink_counter / effective_duration) if effective_duration > 0 else 0,
                            'alert_count': self.session_data['alert_count'],
                            'current_avg_ear': current_avg_ear,
                            'current_focus_percent': current_focus,
                            'samples_collected': len(self.ear_samples)
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
