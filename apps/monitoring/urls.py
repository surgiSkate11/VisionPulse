from django.urls import path
from . import views
from .views.config_views import get_user_config
from .views.alert_config_views import get_alert_config

app_name = 'monitoring'

urlpatterns = [
    # --- Vistas HTML ---
    # La página principal de monitoreo en vivo
    path('', views.LiveMonitoringView.as_view(), name='live_session'),
    
    # El historial de sesiones
    path('history/', views.SessionListView.as_view(), name='session_list'),
    
    # El detalle de una sesión
    path('history/<int:pk>/', views.SessionDetailView.as_view(), name='session_detail'),
    
    # --- API Endpoints ---
    path('api/start/', views.start_session, name='api_start'),
    path('api/stop/', views.stop_session, name='api_stop'),
    path('api/metrics/', views.session_metrics, name='api_session_metrics'),
    path('api/pause/', views.pause_monitoring, name='api_pause'),
    path('api/resume/', views.resume_monitoring, name='api_resume'),
    
    # --- User Config ---
    path('api/user-config/', get_user_config, name='api_user_config'),
    
    # --- Recordatorios de Descanso ---
    path('api/snooze-break/', views.snooze_break_reminder, name='api_snooze_break'),
    path('api/break-taken/', views.mark_break_taken, name='api_break_taken'),
    
        # --- Alertas y Ejercicios ---
    path('api/alert-complete-exercise/', views.alert_complete_exercise, name='api_alert_complete_exercise'),
    
    # --- Sistema de Alertas con Cola y Prioridad ---
    path('api/alerts/next/', views.get_next_alert, name='api_get_next_alert'),
    path('api/alerts/notify_played/', views.notify_alert_audio_played, name='api_notify_alert_played'),
    path('api/alerts/acknowledge/', views.acknowledge_alert, name='api_acknowledge_alert'),
    path('api/alerts/resolve-exercise/', views.resolve_alert_with_exercise, name='api_resolve_alert_exercise'),
    path('api/alerts/attach-exercise/', views.attach_exercise_to_alert, name='api_attach_exercise'),
    path('api/alerts/queue-status/', views.get_alert_queue_status, name='api_alert_queue_status'),
    path('api/alerts/cleanup/', views.alert_views.cleanup_alert_queue, name='api_cleanup_alert_queue'),
    path('api/alerts/config/<str:alert_type>/', get_alert_config, name='api_alert_config'),
    
    # --- Configuración de Modelos Mejorados ---
    
    # --- Stream de Video ---
    path('video_feed/', views.video_feed, name='video_feed'),
    
    # --- Diagnóstico ---
    path('api/camera_status/', views.camera_status, name='api_camera_status'),
    
    # --- Server-Sent Events ---
    path('api/alerts/stream/', views.sse_views.alert_stream, name='api_alert_stream'),
]