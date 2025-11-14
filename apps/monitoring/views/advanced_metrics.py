"""
Sistema de Métricas Avanzadas - VisionPulse v2.0

Proporciona análisis avanzado de métricas de monitoreo:
- Análisis de fatiga visual con algoritmos adaptativos
- Detección de patrones de comportamiento
- Predicción temprana de somnolencia
- Métricas de calidad de sesión
"""

import numpy as np
from collections import deque
from typing import Dict, Any, List, Optional, Tuple
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


@dataclass
class MetricWindow:
    """Ventana de métricas con análisis estadístico"""
    values: deque
    window_size: int
    
    def add(self, value: float):
        self.values.append(value)
        
    def mean(self) -> float:
        return np.mean(list(self.values)) if self.values else 0.0
    
    def std(self) -> float:
        return np.std(list(self.values)) if len(self.values) > 1 else 0.0
    
    def trend(self) -> str:
        """Calcula tendencia: 'rising', 'falling', 'stable'"""
        if len(self.values) < 10:
            return 'stable'
        
        first_half = np.mean(list(self.values)[:len(self.values)//2])
        second_half = np.mean(list(self.values)[len(self.values)//2:])
        diff = second_half - first_half
        
        threshold = self.std() * 0.5
        
        if diff > threshold:
            return 'rising'
        elif diff < -threshold:
            return 'falling'
        return 'stable'
    
    def is_stable(self, threshold: float = 0.2) -> bool:
        """Determina si la métrica es estable (baja varianza)"""
        if len(self.values) < 5:
            return True
        return self.std() < threshold


class AdvancedMetricsAnalyzer:
    """
    Analizador avanzado de métricas de monitoreo.
    
    Capacidades:
    - Detección de fatiga visual progresiva
    - Análisis de patrones de parpadeo
    - Predicción de microsueño
    - Score de calidad de sesión
    """
    
    def __init__(self, window_duration: int = 60):
        """
        Args:
            window_duration: Duración de ventana de análisis en segundos
        """
        self.window_duration = window_duration
        
        # Ventanas de métricas (60 segundos aprox con 1 muestra/seg)
        self.ear_window = MetricWindow(deque(maxlen=60), 60)
        self.blink_rate_window = MetricWindow(deque(maxlen=60), 60)
        self.focus_window = MetricWindow(deque(maxlen=60), 60)
        self.head_yaw_window = MetricWindow(deque(maxlen=60), 60)
        self.head_pitch_window = MetricWindow(deque(maxlen=60), 60)
        
        # Estado de alertas
        self.fatigue_score = 0.0
        self.drowsiness_score = 0.0
        self.distraction_score = 0.0
        
        # Timestamps
        self.last_analysis_time = datetime.now()
        self.session_start_time = datetime.now()
        
    def add_metrics(self, metrics: Dict[str, Any]):
        """
        Añade métricas actuales a las ventanas de análisis.
        
        Args:
            metrics: Dict con métricas del frame actual
        """
        self.ear_window.add(metrics.get('avg_ear', 0.25))
        self.blink_rate_window.add(metrics.get('blink_rate', 15.0))
        self.focus_window.add(metrics.get('focus_score', 50.0))
        self.head_yaw_window.add(metrics.get('head_yaw', 0.0))
        self.head_pitch_window.add(metrics.get('head_pitch', 0.0))
        
    def analyze_fatigue(self) -> Tuple[float, str]:
        """
        Analiza indicadores de fatiga visual.
        
        Indicadores:
        - Reducción progresiva de EAR
        - Aumento de tasa de parpadeo
        - Reducción de estabilidad de enfoque
        
        Returns:
            Tuple[float, str]: (fatigue_score 0-100, severity_level)
        """
        fatigue_indicators = []
        
        # 1. Análisis de EAR
        ear_trend = self.ear_window.trend()
        if ear_trend == 'falling':
            fatigue_indicators.append(25)
        
        mean_ear = self.ear_window.mean()
        if mean_ear < 0.22:  # EAR bajo indica ojos cansados
            fatigue_indicators.append(20)
        
        # 2. Análisis de tasa de parpadeo
        mean_blink_rate = self.blink_rate_window.mean()
        if mean_blink_rate < 10:  # Parpadeo muy bajo (olvido de parpadear)
            fatigue_indicators.append(30)
        elif mean_blink_rate > 30:  # Parpadeo excesivo (irritación)
            fatigue_indicators.append(25)
        
        # 3. Análisis de enfoque
        if not self.focus_window.is_stable(threshold=15.0):
            fatigue_indicators.append(15)  # Enfoque inestable
        
        mean_focus = self.focus_window.mean()
        if mean_focus < 60:
            fatigue_indicators.append(10)
        
        # Calcular score final
        fatigue_score = min(100.0, sum(fatigue_indicators))
        
        # Determinar severidad
        if fatigue_score >= 70:
            severity = 'high'
        elif fatigue_score >= 40:
            severity = 'medium'
        elif fatigue_score >= 20:
            severity = 'low'
        else:
            severity = 'none'
        
        self.fatigue_score = fatigue_score
        return fatigue_score, severity
    
    def analyze_drowsiness(self) -> Tuple[float, str]:
        """
        Analiza indicadores de somnolencia.
        
        Indicadores clave:
        - PERCLOS (Percentage of Eye Closure)
        - Parpadeos prolongados
        - Micro-movimientos de cabeza
        
        Returns:
            Tuple[float, str]: (drowsiness_score 0-100, risk_level)
        """
        drowsiness_indicators = []
        
        # 1. PERCLOS: Porcentaje de tiempo con ojos cerrados
        ear_values = list(self.ear_window.values)
        if ear_values:
            perclos = (sum(1 for ear in ear_values if ear < 0.20) / len(ear_values)) * 100
            
            if perclos > 15:  # Más del 15% del tiempo con ojos cerrados
                drowsiness_indicators.append(40)
            elif perclos > 8:
                drowsiness_indicators.append(25)
        
        # 2. Variabilidad de EAR (fluctuaciones grandes indican lucha por mantener despierto)
        if self.ear_window.std() > 0.05:
            drowsiness_indicators.append(20)
        
        # 3. Movimientos de cabeza (cabeceo por somnolencia)
        pitch_std = self.head_pitch_window.std()
        if pitch_std > 8.0:  # Movimientos grandes de cabeza
            drowsiness_indicators.append(30)
        
        # 4. Tasa de parpadeo muy baja (microsueño inminente)
        mean_blink_rate = self.blink_rate_window.mean()
        if mean_blink_rate < 8:
            drowsiness_indicators.append(25)
        
        # Score final
        drowsiness_score = min(100.0, sum(drowsiness_indicators))
        
        # Nivel de riesgo
        if drowsiness_score >= 60:
            risk = 'critical'
        elif drowsiness_score >= 35:
            risk = 'high'
        elif drowsiness_score >= 15:
            risk = 'moderate'
        else:
            risk = 'low'
        
        self.drowsiness_score = drowsiness_score
        return drowsiness_score, risk
    
    def analyze_distraction(self) -> Tuple[float, List[str]]:
        """
        Analiza patrones de distracción.
        
        Returns:
            Tuple[float, List[str]]: (distraction_score, list of distraction_types)
        """
        distraction_score = 0.0
        distraction_types = []
        
        # 1. Análisis de enfoque
        mean_focus = self.focus_window.mean()
        if mean_focus < 50:
            distraction_score += 30
            distraction_types.append('low_focus')
        
        # 2. Variabilidad de dirección de mirada
        yaw_std = self.head_yaw_window.std()
        if yaw_std > 10.0:
            distraction_score += 25
            distraction_types.append('head_movement')
        
        # 3. Tendencia de enfoque decreciente
        if self.focus_window.trend() == 'falling':
            distraction_score += 20
            distraction_types.append('declining_attention')
        
        # 4. Sesión prolongada sin descansos
        session_duration = (datetime.now() - self.session_start_time).total_seconds() / 60
        if session_duration > 45:  # Más de 45 minutos
            distraction_score += 15
            distraction_types.append('extended_session')
        
        self.distraction_score = min(100.0, distraction_score)
        return self.distraction_score, distraction_types
    
    def get_session_quality_score(self) -> Dict[str, Any]:
        """
        Calcula un score de calidad general de la sesión.
        
        Returns:
            Dict con métricas de calidad:
            - overall_quality: float (0-100)
            - quality_grade: str ('A', 'B', 'C', 'D', 'F')
            - recommendations: List[str]
        """
        # Pesos para cada componente
        weights = {
            'focus': 0.4,
            'blink_health': 0.2,
            'posture': 0.2,
            'stability': 0.2
        }
        
        # 1. Score de enfoque
        focus_score = self.focus_window.mean()
        
        # 2. Score de salud de parpadeo (óptimo: 12-20 parpadeos/min)
        blink_rate = self.blink_rate_window.mean()
        if 12 <= blink_rate <= 20:
            blink_health_score = 100
        elif 8 <= blink_rate <= 25:
            blink_health_score = 70
        else:
            blink_health_score = 40
        
        # 3. Score de postura (cabeza centrada)
        mean_yaw = abs(self.head_yaw_window.mean())
        mean_pitch = abs(self.head_pitch_window.mean())
        posture_deviation = np.sqrt(mean_yaw**2 + mean_pitch**2)
        posture_score = max(0, 100 - posture_deviation * 2)
        
        # 4. Score de estabilidad
        focus_stable = self.focus_window.is_stable(threshold=15.0)
        blink_stable = self.blink_rate_window.is_stable(threshold=5.0)
        stability_score = ((focus_stable * 50) + (blink_stable * 50))
        
        # Calcular score final ponderado
        overall_quality = (
            focus_score * weights['focus'] +
            blink_health_score * weights['blink_health'] +
            posture_score * weights['posture'] +
            stability_score * weights['stability']
        )
        
        # Determinar grado
        if overall_quality >= 90:
            grade = 'A'
        elif overall_quality >= 80:
            grade = 'B'
        elif overall_quality >= 70:
            grade = 'C'
        elif overall_quality >= 60:
            grade = 'D'
        else:
            grade = 'F'
        
        # Generar recomendaciones
        recommendations = []
        if focus_score < 70:
            recommendations.append("Reduce distracciones en tu entorno")
        if blink_rate < 10:
            recommendations.append("Parpadea más frecuentemente para evitar ojo seco")
        if blink_rate > 25:
            recommendations.append("Tasa de parpadeo elevada - revisa iluminación")
        if posture_deviation > 20:
            recommendations.append("Ajusta tu postura para mirar la pantalla de frente")
        if not focus_stable:
            recommendations.append("Tu atención fluctúa - considera tomar un descanso")
        
        return {
            'overall_quality': round(overall_quality, 2),
            'quality_grade': grade,
            'focus_score': round(focus_score, 2),
            'blink_health_score': round(blink_health_score, 2),
            'posture_score': round(posture_score, 2),
            'stability_score': round(stability_score, 2),
            'recommendations': recommendations,
            'fatigue_score': round(self.fatigue_score, 2),
            'drowsiness_score': round(self.drowsiness_score, 2),
            'distraction_score': round(self.distraction_score, 2),
        }
    
    def get_comprehensive_analysis(self) -> Dict[str, Any]:
        """
        Realiza un análisis comprehensivo de todas las métricas.
        
        Returns:
            Dict completo con todos los análisis
        """
        fatigue_score, fatigue_severity = self.analyze_fatigue()
        drowsiness_score, drowsiness_risk = self.analyze_drowsiness()
        distraction_score, distraction_types = self.analyze_distraction()
        session_quality = self.get_session_quality_score()
        
        return {
            'fatigue': {
                'score': fatigue_score,
                'severity': fatigue_severity,
            },
            'drowsiness': {
                'score': drowsiness_score,
                'risk_level': drowsiness_risk,
            },
            'distraction': {
                'score': distraction_score,
                'types': distraction_types,
            },
            'session_quality': session_quality,
            'timestamp': datetime.now().isoformat(),
        }
