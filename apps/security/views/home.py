
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView
from django.db.models import Sum, Count, Avg, Q
from django.utils import timezone
from datetime import timedelta
from apps.security.components.sidebar_menu_mixin import SidebarMenuMixin
from apps.monitoring.models import MonitorSession, AlertEvent
from apps.exercises.models import ExerciseSession


class HomeView(LoginRequiredMixin, SidebarMenuMixin, TemplateView):
    template_name = 'home.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Dashboard'
        
        user = self.request.user
        
        # Obtener datos de los últimos 7 días para el gráfico
        end_date = timezone.now()
        start_date = end_date - timedelta(days=6)
        
        # Tiempo total de pantalla (últimos 7 días)
        sessions = MonitorSession.objects.filter(
            user=user,
            start_time__gte=start_date
        )
        
        total_duration = sessions.aggregate(
            total=Sum('total_duration')
        )['total'] or 0
        
        if total_duration == 0:
            total_duration = sessions.aggregate(
                total=Sum('duration_seconds')
            )['total'] or 0

        # Promedio diario de horas de pantalla en los últimos 7 días
        total_hours = round((total_duration / 3600) / 7, 1) if total_duration else 0
        
        # Ritmo de parpadeo promedio (por minuto)
        total_blinks = sessions.aggregate(total=Sum('total_blinks'))['total'] or 0
        total_duration = sessions.aggregate(total=Sum('total_duration'))['total'] or 0
        total_minutes = total_duration / 60 if total_duration else 0

        if total_blinks > 0 and total_minutes > 0:
            avg_blink_rate = round(total_blinks / total_minutes, 1)
        else:
            avg_blink_rate = 0
        
        # Pausas recomendadas vs realizadas (HOY) para reflejar el diseño
        start_of_today = end_date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_today = start_of_today + timedelta(days=1)

        recommended_breaks = MonitorSession.objects.filter(
            user=user,
            start_time__gte=start_of_today,
            start_time__lt=end_of_today,
        ).count()  # 1 pausa recomendada por sesión del día

        completed_breaks = ExerciseSession.objects.filter(
            user=user,
            started_at__gte=start_of_today,
            started_at__lt=end_of_today,
            completed=True
        ).count()
        
        # Alertas recientes
        recent_alerts = AlertEvent.objects.filter(
            session__user=user
        ).order_by('-triggered_at')[:5]
        
        # Estado visual (basado en alertas de fatiga)
        fatigue_alerts = AlertEvent.objects.filter(
            session__user=user,
            alert_type='fatigue',
            triggered_at__gte=start_date
        ).count()
        
        # Calcular estado (0-100)
        visual_status = max(0, 100 - (fatigue_alerts * 10))
        # Calcular posición del indicador de progreso visual
        progress_right = max(0, min(100, 100 - visual_status))
        
        # Datos para el gráfico de parpadeo (últimos 7 días)
        chart_data = []
        chart_labels = []
        breaks_chart_data = []
        
        for i in range(7):
            day = start_date + timedelta(days=i)
            day_end = day + timedelta(days=1)
            
            day_sessions = MonitorSession.objects.filter(
                user=user,
                start_time__gte=day,
                start_time__lt=day_end,
                total_blinks__gt=0
            )
            
            if day_sessions.exists():
                avg_blinks_day = day_sessions.aggregate(
                    avg=Avg('total_blinks')
                )['avg']
                blink_rate = round((avg_blinks_day or 0) / 60, 1)
            else:
                blink_rate = 0
            
            chart_data.append(blink_rate)
            chart_labels.append(day.strftime('%d/%m'))

            # Descansos realizados por día (ejercicios completados)
            day_breaks = ExerciseSession.objects.filter(
                user=user,
                started_at__gte=day,
                started_at__lt=day_end,
                completed=True
            ).count()
            breaks_chart_data.append(day_breaks)
        
        import json
        context.update({
            'total_hours': total_hours,
            'avg_blink_rate': avg_blink_rate,
            'completed_breaks': completed_breaks,
            'recommended_breaks': recommended_breaks,
            'visual_status': visual_status,
            'progress_right': progress_right,
            'recent_alerts': recent_alerts,
            'chart_data': json.dumps(chart_data),
            'chart_labels': json.dumps(chart_labels),
            'breaks_chart_data': json.dumps(breaks_chart_data),
            # Estadísticas de Salud Visual del Usuario
            'user_total_monitoring_time': user.total_monitoring_time,
            'user_total_sessions': user.total_sessions,
            'user_current_streak': user.current_streak,
            'user_longest_streak': user.longest_streak,
            'user_exercises_completed': user.exercises_completed,
            # breaks_taken eliminado: usar exercises_completed
            'user_fatigue_episodes': user.fatigue_episodes,
        })
        
        return context