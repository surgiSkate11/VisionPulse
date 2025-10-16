from django.urls import path
from . import views
from apps.monitoring.views import ModuloTemplateView, SessionListView, SessionDetailView

app_name = 'monitoring'

urlpatterns = [
    path('home/', ModuloTemplateView.as_view(), name='home'),
    path('sessions/', SessionListView.as_view(), name='session_list'),
    path('sessions/<int:session_id>/', SessionDetailView.as_view(), name='session_detail'),
    
    # API endpoints
    path('api/start/', views.start_session, name='api_start'),
    path('api/upload_frame/', views.upload_frame, name='api_upload_frame'),
    path('api/stop/', views.stop_session, name='api_stop'),
]