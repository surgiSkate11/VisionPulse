from django.urls import path
from . import views
from apps.monitoring.views import ModuloTemplateView, SessionListView, SessionDetailView

app_name = 'monitoring'

urlpatterns = [
    path('home/', ModuloTemplateView.as_view(), name='home'),
    #path('real-time/', views.RealTimeMonitoringView.as_view(), name='real_time_monitoring'),
    path('sessions/', SessionListView.as_view(), name='session_list'),
    path('sessions/<int:session_id>/', SessionDetailView.as_view(), name='session_detail'),
    
    # API endpoints
    path('api/start/', views.start_session, name='api_start'),
    #path('api/upload_frame/', views.upload_frame, name='api_upload_frame'),
    path('api/stop/', views.stop_session, name='api_stop'),
    
    
    path('webcam-test/', views.WebcamTestView.as_view(), name='webcam_test'),
    path('video_feed/', views.video_feed, name='video_feed'),
    path('start-webcam-test/', views.start_webcam_test, name='start_webcam_test'),
    path('stop-webcam-test/', views.stop_webcam_test, name='stop_webcam_test'),
    path('session-metrics/', views.session_metrics, name='api_session_metrics')
]