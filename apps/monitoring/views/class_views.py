"""
Class-based Views - Vistas basadas en clases para páginas HTML
Este módulo contiene todas las vistas basadas en clases (TemplateView, ListView, DetailView)
"""

from datetime import timedelta

from django.views.generic import TemplateView, ListView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin

from apps.security.components.sidebar_menu_mixin import SidebarMenuMixin
from ..models import MonitorSession
from .controller import controller


class LiveMonitoringView(LoginRequiredMixin, SidebarMenuMixin, TemplateView):
    """Vista principal para el monitoreo en vivo."""
    template_name = 'monitoring/live_session.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Monitoreo en Vivo'
        context['active_session'] = False
        
        if controller.camera_manager and controller.camera_manager.is_running:
            context['active_session'] = True
            context['session_id'] = controller.camera_manager.session_id
            context['is_paused'] = controller.camera_manager.is_paused
            
            try:
                if controller.camera_manager.session_id:
                    session = MonitorSession.objects.get(
                        id=controller.camera_manager.session_id
                    )
                    context['total_blinks'] = session.total_blinks
                    context['start_time'] = session.start_time
            except MonitorSession.DoesNotExist:
                pass
                
        return context


class SessionListView(LoginRequiredMixin, SidebarMenuMixin, ListView):
    model = MonitorSession
    template_name = 'monitoring/session_list.html'
    context_object_name = 'sessions'
    
    def get_queryset(self):
        return MonitorSession.objects.filter(user=self.request.user).order_by('-start_time')


class SessionDetailView(LoginRequiredMixin, SidebarMenuMixin, DetailView):
    model = MonitorSession
    template_name = 'monitoring/session_detail.html'
    context_object_name = 'session'
    
    def get_queryset(self):
        return MonitorSession.objects.filter(user=self.request.user)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        session = self.object
        
        # Datos para los gráficos (solo AlertEvents)
        alerts = list(session.alerts.all().order_by('timestamp'))

        # Combinar eventos para la tabla (solo alertas)
        all_events = []
        for alert in alerts:
            all_events.append({
                'timestamp': alert.timestamp,
                'type': 'alert',
                'description': alert.description
            })

        # Ordenar eventos por timestamp
        all_events.sort(key=lambda x: x['timestamp'], reverse=True)

        # Generar etiquetas de tiempo y datos
        time_labels = []
        focus_data = []

        if session.start_time and session.end_time:
            duration = (session.end_time - session.start_time).total_seconds()
            interval = max(1, int(duration / 30))  # 30 puntos máximo en el gráfico

            current_time = session.start_time
            while current_time <= session.end_time:
                time_labels.append(current_time.strftime('%H:%M:%S'))

                # Estado de atención en este intervalo
                alerts_in_interval = [
                    alert for alert in alerts 
                    if alert.timestamp <= current_time and alert.alert_type == 'distraction'
                ]
                focus_data.append(100 if not alerts_in_interval else 50)

                current_time += timedelta(seconds=interval)

        context.update({
            'time_labels': time_labels,
            'focus_data': focus_data,
            'events': all_events,  # Solo alertas
            'total_duration': session.total_duration if session.total_duration else 0,
            'effective_duration': session.effective_duration if session.effective_duration else 0,
            'total_blinks': session.total_blinks if session.total_blinks else 0,
            'total_alerts': session.total_alerts if session.total_alerts else 0,
            'page_title': f'Sesión #{session.id}'
        })
        
        return context
