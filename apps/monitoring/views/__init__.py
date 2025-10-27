# apps/monitoring/views/__init__.py
"""
Módulo de vistas para el sistema de monitoreo.
"""

# Importar clases de detección y gestión de cámara
from .camera import BlinkDetector, EyePoints, CameraManager

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
    mark_break_taken
)

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
]
