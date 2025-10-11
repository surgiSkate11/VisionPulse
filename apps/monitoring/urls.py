from django.urls import path
from . import views
from apps.monitoring.views import ModuloTemplateView

app_name = 'monitoring'

urlpatterns = [
    # URLs para monitoreo - a implementar más tarde
    # path('sessions/', views.session_list, name='session_list'),
    # path('alerts/', views.alert_list, name='alert_list'),
    path('home/', ModuloTemplateView.as_view(), name='home'),
    
]