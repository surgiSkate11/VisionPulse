from django.urls import path
from . import views

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
    
    # --- Recordatorios de Descanso ---
    path('api/snooze_break/', views.snooze_break_reminder, name='api_snooze_break'),
    path('api/break_taken/', views.mark_break_taken, name='api_break_taken'),
    
    # --- Configuración de Modelos Mejorados ---
    # Ruta eliminada: validación de configuración avanzada per-user ya no aplica

    # --- Stream de Video ---
    path('video_feed/', views.video_feed, name='video_feed'),
    
    # --- Diagnóstico ---
    path('api/camera_status/', views.camera_status, name='api_camera_status'),
]