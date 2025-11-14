"""
Lógica de detección de alertas con ventanas deslizantes, sustain, histéresis y cooldown.
Cada tipo de alerta puede tener su propia configuración.
"""
import time
import numpy as np
from collections import deque, defaultdict

class SlidingWindow:
    """Ventana deslizante para cálculos de promedio, conteo, varianza, etc."""
    def __init__(self, maxlen):
        self.data = deque(maxlen=maxlen)
    def append(self, value):
        self.data.append(value)
    def mean(self):
        return np.mean(self.data) if self.data else 0.0
    def std(self):
        return np.std(self.data) if self.data else 0.0
    def count(self):
        return len(self.data)
    def sum(self):
        return np.sum(self.data) if self.data else 0.0
    def clear(self):
        self.data.clear()

def ewma(data, alpha=0.3):
    """Promedio móvil exponencial"""
    if not data:
        return 0.0
    avg = data[0]
    for x in data[1:]:
        avg = alpha * x + (1 - alpha) * avg
    return avg

class AlertDetectionEngine:
    """
    Motor profesional para detección de alertas, parametrizado y eficiente.
    Centraliza la lógica de las 10 alertas principales.
    """
    def __init__(self, config):
        self.config = config
        self.sustain_start = {}
        self.hysteresis_start = {}
        self.alert_active = {}
        self.occurrences = defaultdict(int)
        self.windows = defaultdict(lambda: None)
        self.distraction_events = deque(maxlen=100)
        self.pose_samples = deque(maxlen=180)
        self.session_start = None

    def update(self, alert_type, sensors, timestamp=None):
        """
        Actualiza el motor con los datos de sensores para el tipo de alerta.
        Args:
            alert_type: str
            sensors: dict con datos relevantes
            timestamp: float
        Returns: 'trigger', 'resolve', None
        """
        if timestamp is None:
            timestamp = time.time()
        cfg = self.config.get(alert_type, {})

        # Microsueño
        if alert_type == 'microsleep':
            eyes_closed = sensors.get('eyes_closed', False)
            # 🔥 USAR EL THRESHOLD DINÁMICO DEL USUARIO (microsleep_duration_seconds)
            # Si viene en sensors, usar ese; si no, usar el default del config
            sustain = sensors.get('threshold', cfg.get('sustain', 5.0))
            return self._sustain_logic(alert_type, eyes_closed, sustain, timestamp)

        # Fatiga Visual
        if alert_type == 'fatigue':
            ear = sensors.get('ear', 1.0)
            blink_rate = sensors.get('blink_rate', 10)
            microsleep_active = sensors.get('microsleep_active', False)
            sustain = cfg.get('sustain', 10.0)
            # "Parpadeo normal" ahora se define como >= 15 por minuto
            condition = (ear < cfg.get('ear_threshold', 0.15) and blink_rate >= cfg.get('blink_rate_min', 15) and not microsleep_active)
            return self._sustain_logic(alert_type, condition, sustain, timestamp)

        # Parpadeo Bajo
        if alert_type == 'low_blink_rate':
            blink_rate = sensors.get('blink_rate', 0)
            ewma_rate = sensors.get('ewma_blink_rate', 0)
            sustain = cfg.get('sustain', 60)
            # 🔥 v7.0: Umbral optimizado: < 12 (antes 15 era muy estricto)
            threshold = cfg.get('threshold', 12)
            window = self._get_window(alert_type, cfg.get('window', 120))
            window.append(blink_rate)
            condition = (window.mean() < threshold and ewma(list(window.data)) < threshold)
            return self._sustain_logic(alert_type, condition, sustain, timestamp)

        # Parpadeo Excesivo
        if alert_type == 'high_blink_rate':
            br_120 = sensors.get('blink_rate_120', 0)
            br_30 = sensors.get('blink_rate_30', 0)
            sustain = cfg.get('sustain', 30)
            # 🔥 v7.0: Thresholds optimizados: 30/28 (antes 40/35 era demasiado alto)
            t1 = cfg.get('threshold1', 30)  # Ventana larga 120s
            t2 = cfg.get('threshold2', 28)  # Ventana corta 30s
            w1 = self._get_window(alert_type+'_120', 120)
            w2 = self._get_window(alert_type+'_30', 30)
            w1.append(br_120)
            w2.append(br_30)
            condition = (w1.mean() > t1 and w2.mean() > t2)
            return self._sustain_logic(alert_type, condition, sustain, timestamp)

        # Usuario Ausente
        if alert_type == 'driver_absent':
            face_detected = sensors.get('face_detected', True)
            sustain = cfg.get('sustain', 2.0)
            hysteresis = cfg.get('hysteresis', 5.0)
            return self._hysteresis_logic(alert_type, not face_detected, sustain, hysteresis, timestamp)

        # Múltiples Personas
        if alert_type == 'multiple_people':
            n_faces = sensors.get('num_faces', 1)
            sustain = cfg.get('sustain', 1.5)
            hysteresis = cfg.get('hysteresis', 5.0)
            return self._hysteresis_logic(alert_type, n_faces > 1, sustain, hysteresis, timestamp)

        # Cámara Obstruida
        if alert_type == 'camera_occluded':
            # 🎯 USAR LA CONDICIÓN QUE VIENE DESDE EL CONTROLLER
            # El controller calcula occlusion_effective de forma más completa
            condition = sensors.get('condition', False)
            sustain = cfg.get('sustain', 2.5)
            hysteresis = cfg.get('hysteresis', 5.0)
            
            # 🔥 LOG CRÍTICO DEL MOTOR
            import logging
            print(f"\n🔧 [MOTOR] camera_occluded: condition={condition}, sustain={sustain}s, hysteresis={hysteresis}s\n")
            logging.info(f"[MOTOR-EVAL] camera_occluded: condition={condition} (desde controller)")
            logging.info(f"[MOTOR-EVAL] sustain={sustain}s, hysteresis={hysteresis}s")
            
            result = self._hysteresis_logic(alert_type, condition, sustain, hysteresis, timestamp)
            print(f"\n⚙️ [MOTOR] _hysteresis_logic retornó: '{result}'\n")
            logging.info(f"[MOTOR-EVAL] _hysteresis_logic retornó: '{result}'")
            return result

        # Distracción Frecuente
        if alert_type == 'frequent_distraction':
            distraction_event = sensors.get('distraction_event', False)
            window_sec = cfg.get('window', 300)
            min_events = cfg.get('min_events', 4)
            now = timestamp
            if distraction_event:
                self.distraction_events.append(now)
            # Contar eventos en ventana móvil
            self.distraction_events = deque([t for t in self.distraction_events if now - t <= window_sec], maxlen=100)
            if len(self.distraction_events) >= min_events:
                return 'trigger'
            return None

        # Somnolencia Temprana
        if alert_type == 'micro_rhythm':
            score = sensors.get('score', 0)
            threshold = cfg.get('score_threshold', 50)
            if score >= threshold:
                return self._sustain_logic(alert_type, True, 5.0, timestamp)
            return self._sustain_logic(alert_type, False, 5.0, timestamp)

        # Tensión en Cuello
        if alert_type == 'head_tension':
            variance_threshold = cfg.get('variance_threshold', 2.0)
            sustain_s = 10.0
            # Camino 1: usar varianza precomputada si viene en sensores
            if 'std_yaw' in sensors and 'std_pitch' in sensors:
                session_time = sensors.get('session_time', 0)
                if session_time < cfg.get('min_session', 600):
                    return None
                total_var = float(sensors.get('std_yaw', 0.0)) + float(sensors.get('std_pitch', 0.0))
                condition = total_var < variance_threshold
                return self._sustain_logic(alert_type, condition, sustain_s, timestamp)

            # Camino 2: acumular muestras crudas y calcular internamente
            yaw = sensors.get('yaw', 0.0)
            pitch = sensors.get('pitch', 0.0)
            session_time = sensors.get('session_time', 0)
            min_samples = cfg.get('min_samples', 10)
            window_sec = cfg.get('window', 180)
            if self.session_start is None:
                self.session_start = timestamp - session_time
            self.pose_samples.append((yaw, pitch, timestamp))
            samples = [(y, p) for y, p, t in self.pose_samples if timestamp - t <= window_sec]
            if len(samples) >= min_samples and (timestamp - self.session_start) >= cfg.get('min_session', 600):
                yaws = [y for y, _ in samples]
                pitches = [p for _, p in samples]
                total_var = float(np.std(yaws)) + float(np.std(pitches))
                condition = total_var < variance_threshold
                return self._sustain_logic(alert_type, condition, sustain_s, timestamp)
            return None

        return None

    def _sustain_logic(self, alert_type, condition, sustain, timestamp):
        if condition:
            if alert_type not in self.sustain_start:
                self.sustain_start[alert_type] = timestamp
            if (timestamp - self.sustain_start[alert_type]) >= sustain and not self.alert_active.get(alert_type, False):
                self.alert_active[alert_type] = True
                return 'trigger'
        else:
            self.sustain_start.pop(alert_type, None)
            if self.alert_active.get(alert_type, False):
                self.alert_active[alert_type] = False
                return 'resolve'
        return None

    def _hysteresis_logic(self, alert_type, condition, sustain, hysteresis, timestamp):
        import logging
        
        is_active = self.alert_active.get(alert_type, False)
        sustain_start = self.sustain_start.get(alert_type)
        hysteresis_start = self.hysteresis_start.get(alert_type)
        
        print(f"⏱️ [HYSTERESIS] {alert_type}: condition={condition}, is_active={is_active}")
        logging.info(f"[HYSTERESIS] {alert_type}: condition={condition}, is_active={is_active}, sustain_start={sustain_start}, hysteresis_start={hysteresis_start}")
        
        if condition:
            # Condición se cumple
            self.hysteresis_start.pop(alert_type, None)
            if alert_type not in self.sustain_start:
                self.sustain_start[alert_type] = timestamp
                print(f"🟡 [HYSTERESIS] {alert_type}: Iniciando sustain en timestamp={timestamp}")
                logging.info(f"[HYSTERESIS] {alert_type}: Iniciando sustain, start={timestamp}")
            
            time_in_sustain = timestamp - self.sustain_start[alert_type]
            print(f"⏱️ [HYSTERESIS] {alert_type}: time_in_sustain={time_in_sustain:.1f}s, sustain_required={sustain}s")
            logging.info(f"[HYSTERESIS] {alert_type}: time_in_sustain={time_in_sustain:.1f}s, sustain_required={sustain}s")
            
            if time_in_sustain >= sustain and not is_active:
                self.alert_active[alert_type] = True
                print(f"✅✅✅ [HYSTERESIS] {alert_type}: TRIGGER!!! (sustain cumplido, activando alerta) ✅✅✅\n")
                logging.info(f"[HYSTERESIS] {alert_type}: ✅ TRIGGER (sustain cumplido)")
                return 'trigger'
            elif is_active:
                print(f"ℹ️ [HYSTERESIS] {alert_type}: Ya está activa")
                logging.info(f"[HYSTERESIS] {alert_type}: Ya está activa, retornando None")
        else:
            # Condición NO se cumple
            print(f"🔵 [HYSTERESIS] {alert_type}: Condición NO se cumple (condition=False)")
            self.sustain_start.pop(alert_type, None)
            if is_active:
                print(f"⚠️ [HYSTERESIS] {alert_type}: Alerta está ACTIVA pero condition=False → iniciando resolución")
                if alert_type not in self.hysteresis_start:
                    self.hysteresis_start[alert_type] = timestamp
                    print(f"🔄 [HYSTERESIS] {alert_type}: Iniciando hysteresis en timestamp={timestamp}")
                    logging.info(f"[HYSTERESIS] {alert_type}: Iniciando hysteresis, start={timestamp}")
                
                time_in_hysteresis = timestamp - self.hysteresis_start[alert_type]
                remaining = hysteresis - time_in_hysteresis
                print(f"⏳ [HYSTERESIS] {alert_type}: time={time_in_hysteresis:.1f}s, required={hysteresis}s, remaining={remaining:.1f}s")
                logging.info(f"[HYSTERESIS] {alert_type}: time_in_hysteresis={time_in_hysteresis:.1f}s, hysteresis_required={hysteresis}s, remaining={remaining:.1f}s")
                
                if time_in_hysteresis >= hysteresis:
                    self.alert_active[alert_type] = False
                    self.hysteresis_start.pop(alert_type, None)
                    print(f"✅ [HYSTERESIS] {alert_type}: RESOLVE (hysteresis cumplido)\n")
                    logging.info(f"[HYSTERESIS] {alert_type}: ✅ RESOLVE (hysteresis cumplido)")
                    return 'resolve'
                else:
                    logging.info(f"[HYSTERESIS] {alert_type}: ⏳ Esperando resolución, faltan {remaining:.1f}s")
            else:
                print(f"ℹ️ [HYSTERESIS] {alert_type}: Alerta NO activa y condition=False → sin acción")
        
        logging.info(f"[HYSTERESIS] {alert_type}: Retornando None")
        return None

    def _get_window(self, key, size):
        if self.windows[key] is None:
            self.windows[key] = SlidingWindow(size)
        return self.windows[key]

    def resolve_alert(self, alert_type):
        self.alert_active[alert_type] = False
        self.sustain_start.pop(alert_type, None)
        self.hysteresis_start.pop(alert_type, None)
        self.occurrences[alert_type] = 0
        if self.windows.get(alert_type):
            self.windows[alert_type].clear()

    def is_active(self, alert_type):
        return self.alert_active.get(alert_type, False)

    def reset(self, alert_type):
        self.sustain_start.pop(alert_type, None)
        self.hysteresis_start.pop(alert_type, None)
        self.alert_active.pop(alert_type, None)
        self.occurrences[alert_type] = 0
        if self.windows.get(alert_type):
            self.windows[alert_type].clear()

    def reset_all(self):
        self.sustain_start.clear()
        self.hysteresis_start.clear()
        self.alert_active.clear()
        self.occurrences.clear()
        self.windows.clear()
        self.distraction_events.clear()
        self.pose_samples.clear()
        self.session_start = None

"""
Uso profesional:
from apps.monitoring.utils.alert_detection import AlertDetectionEngine

ALERT_CONFIG = {
    'microsleep': {'sustain': 5.0, 'priority': 1},
    'fatigue': {'sustain': 10.0, 'ear_threshold': 0.15, 'blink_rate_min': 15, 'priority': 1},
    'low_blink_rate': {'window': 120, 'threshold': 15, 'sustain': 60, 'priority': 2},
    'high_blink_rate': {'window1': 120, 'window2': 30, 'threshold1': 40, 'threshold2': 35, 'sustain': 30, 'priority': 2},
    'driver_absent': {'sustain': 2.0, 'hysteresis': 5.0, 'max_occurrences': 3, 'priority': 2},
    'multiple_people': {'sustain': 1.5, 'hysteresis': 5.0, 'priority': 2},
    'camera_occluded': {'sustain': 2.5, 'hysteresis': 5.0, 'priority': 3},
    'frequent_distraction': {'window': 300, 'min_events': 4, 'priority': 3},
    'micro_rhythm': {'score_threshold': 50, 'priority': 3},
    'head_tension': {'window': 180, 'min_samples': 10, 'variance_threshold': 2.0, 'min_session': 600, 'priority': 4},
}

engine = AlertDetectionEngine(ALERT_CONFIG)
# En cada frame/intervalo, llama:
# result = engine.update('microsleep', {'eyes_closed': True}, timestamp)
# if result == 'trigger': ...
"""
