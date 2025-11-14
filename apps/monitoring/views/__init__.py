# apps/monitoring/views/__init__.py
"""
Módulo de vistas para el sistema de monitoreo.
"""

# Importar clases de detección y gestión de cámara
from .camera import EyePoints, CameraManager

# Importar controlador de monitoreo
from .controller import MonitoringController, controller

# Importar vistas basadas en clases (CBV)
from .class_views import (
    LiveMonitoringView,
    SessionListView,
    SessionDetailView
)

# Importar vistas de API
from .api_views import (
    video_feed,
    start_session,
    stop_session,
    pause_monitoring,
    resume_monitoring,
    session_metrics,
    camera_status,
    snooze_break_reminder,
    mark_break_taken,
    alert_complete_exercise
)

# Importar vistas de alertas con cola y prioridad
from .alert_views import (
    get_next_alert,
    notify_alert_audio_played,
    acknowledge_alert,
    resolve_alert_with_exercise,
    attach_exercise_to_alert,
    get_alert_queue_status,
    cleanup_alert_queue,
    audio_diagnostics
)

# Importar vistas SSE
from . import sse_views

__all__ = [
    # Clases de detección
    'BlinkDetector',
    'EyePoints',
    'CameraManager',
    
    # Controlador
    'MonitoringController',
    'controller',
    
    # Vistas basadas en clases
    'LiveMonitoringView',
    'SessionListView',
    'SessionDetailView',
    
    # API views
    'video_feed',
    'start_session',
    'stop_session',
    'pause_monitoring',
    'resume_monitoring',
    'session_metrics',
    'camera_status',
    'snooze_break_reminder',
    'mark_break_taken',
    'alert_complete_exercise',
    
    # Alert views
    'trigger_alert',
    'get_next_alert',
    'notify_alert_audio_played',
    'acknowledge_alert',
    'resolve_alert_with_exercise',
    'attach_exercise_to_alert',
    'get_alert_queue_status',
    'cleanup_alert_queue',
    'audio_diagnostics',
]
