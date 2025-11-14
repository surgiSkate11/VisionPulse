
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView
from django.db.models import Sum, Count, Avg, Q
from django.utils import timezone
from datetime import timedelta
from apps.security.components.sidebar_menu_mixin import SidebarMenuMixin
from apps.monitoring.models import MonitorSession, AlertEvent, SessionPause
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
        
        # Pausas recomendadas vs realizadas (HOY): basadas en tiempo activo e intervalo de descanso del usuario
        start_of_today = end_date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_today = start_of_today + timedelta(days=1)

        from django.db.models import Q as _Q
        today_sessions = (
            MonitorSession.objects
            .filter(user=user)
            .filter(
                _Q(start_time__lt=end_of_today),
                _Q(end_time__gte=start_of_today) | _Q(end_time__isnull=True)
            )
            .prefetch_related('pauses')
        )

        def active_seconds_within(session: MonitorSession, start_dt, end_dt):
            from django.utils import timezone as dj_tz
            s_start = session.start_time
            s_end = session.end_time or dj_tz.localtime()
            w_start = max(start_dt, s_start)
            w_end = min(end_dt, s_end)
            if w_end <= w_start:
                return 0
            total = (w_end - w_start).total_seconds()
            paused = 0.0
            for p in session.pauses.all():
                p_start = p.pause_time
                p_end = p.resume_time or s_end
                o_start = max(w_start, p_start)
                o_end = min(w_end, p_end)
                if o_end > o_start:
                    paused += (o_end - o_start).total_seconds()
            return max(0, int(total - paused))

        active_seconds_today = 0
        for s in today_sessions:
            active_seconds_today += active_seconds_within(s, start_of_today, end_of_today)
        active_minutes_today = active_seconds_today / 60.0

        # Descansos recomendados (alertas de break_reminder generadas hoy)
        recommended_breaks = AlertEvent.objects.filter(
            session__user=user,
            alert_type='break_reminder',
            triggered_at__gte=start_of_today,
            triggered_at__lt=end_of_today
        ).count()

        # Descansos completados (pausas tomadas en sesiones con break_reminder)
        sessions_with_breaks_today = today_sessions.filter(
            alerts__alert_type='break_reminder',
            alerts__triggered_at__gte=start_of_today,
            alerts__triggered_at__lt=end_of_today
        ).distinct()
        
        completed_breaks = SessionPause.objects.filter(
            session__in=sessions_with_breaks_today,
            pause_time__gte=start_of_today,
            pause_time__lt=end_of_today
        ).count()
        
        # Alertas recientes
        recent_alerts = AlertEvent.objects.filter(
            session__user=user
        ).order_by('-triggered_at')[:5]
        
        # ================================================================
        # CÁLCULO PERFECTO DEL ESTADO VISUAL (últimas 24 horas)
        # ================================================================
        # Base: 100 puntos (salud óptima)
        # Se restan puntos por fatiga/alertas y se suman por buenos hábitos
        
        # Ventana de tiempo: últimas 24 horas (estado actual, no histórico)
        last_24h = end_date - timedelta(hours=24)
        
        # 1. Sesiones y métricas de las últimas 24 horas
        recent_sessions = MonitorSession.objects.filter(
            user=user,
            start_time__gte=last_24h
        )
        
        # 2. Alertas críticas recientes (últimas 24h)
        critical_alerts = AlertEvent.objects.filter(
            session__user=user,
            triggered_at__gte=last_24h,
            alert_type__in=['microsleep', 'fatigue', 'camera_occluded']
        ).count()
        
        # 3. Alertas de advertencia recientes (últimas 24h)
        warning_alerts = AlertEvent.objects.filter(
            session__user=user,
            triggered_at__gte=last_24h,
            alert_type__in=['low_blink_rate', 'high_blink_rate', 'frequent_distraction', 
                          'micro_rhythm', 'head_tension', 'multiple_people', 'driver_absent']
        ).count()
        
        # 4. EAR promedio de las sesiones recientes (salud visual real)
        avg_ear_recent = recent_sessions.aggregate(avg=Avg('avg_ear'))['avg']
        if avg_ear_recent is None:
            avg_ear_recent = 0.30  # Valor neutral si no hay datos
        
        # 5. Descansos completados HOY (buenos hábitos)
        breaks_today = ExerciseSession.objects.filter(
            user=user,
            started_at__gte=start_of_today,
            started_at__lt=end_of_today,
            completed=True
        ).count()
        
        # 6. Tasa de parpadeo reciente
        recent_blinks = recent_sessions.aggregate(total=Sum('total_blinks'))['total'] or 0
        recent_duration = recent_sessions.aggregate(total=Sum('total_duration'))['total'] or 0
        recent_minutes = recent_duration / 60 if recent_duration else 0
        recent_blink_rate = recent_blinks / recent_minutes if recent_minutes > 0 else 15
        
        # ================================================================
        # FÓRMULA DE ESTADO VISUAL PERFECCIONADO
        # ================================================================
        # Determinar BASE según si hay actividad reciente (últimas 24h)
        has_recent_activity = recent_sessions.exists()
        
        if has_recent_activity:
            # Si hay actividad reciente: base 75 (neutral, no óptimo)
            visual_status = 75
        else:
            # Si NO hay actividad reciente: base 85 (asumir salud buena)
            visual_status = 85
        
        # Penalizaciones MODERADAS por alertas críticas (microsueño, fatiga, oclusión)
        visual_status -= min(critical_alerts * 8, 30)  # Máx -30 puntos por alertas críticas
        
        # Penalizaciones LEVES por alertas de advertencia
        visual_status -= min(warning_alerts * 3, 20)   # Máx -20 puntos por alertas de advertencia
        
        # Bonus SIGNIFICATIVO por descansos completados hoy
        visual_status += min(breaks_today * 10, 25)    # Máx +25 puntos por descansos
        
        # Solo aplicar penalizaciones de EAR/parpadeo si HAY actividad reciente
        if has_recent_activity:
            # Penalización por EAR bajo (ojos cansados)
            if avg_ear_recent < 0.18:
                visual_status -= 15  # EAR muy bajo = fatiga severa
            elif avg_ear_recent < 0.22:
                visual_status -= 8   # EAR bajo = fatiga moderada
            elif avg_ear_recent >= 0.28:
                visual_status += 5   # EAR alto = ojos descansados
            
            # Penalización/bonus por tasa de parpadeo
            if recent_blink_rate < 8:
                visual_status -= 12  # Parpadeo muy bajo = sequedad ocular
            elif recent_blink_rate < 12:
                visual_status -= 6   # Parpadeo bajo
            elif recent_blink_rate > 28:
                visual_status -= 8   # Parpadeo excesivo = irritación
            elif 15 <= recent_blink_rate <= 20:
                visual_status += 8   # Parpadeo ideal (BONUS aumentado)
        
        # Bonus/penalización por tiempo activo HOY (solo si hay actividad)
        if active_minutes_today > 0:
            if active_minutes_today <= 90:  # 1.5 horas o menos = excelente
                visual_status += 12
            elif active_minutes_today <= 180:  # 2-3 horas = bueno
                visual_status += 5
            elif active_minutes_today > 300:   # más de 5 horas = excesivo
                visual_status -= 12
        
        # Limitar entre 0 y 100
        visual_status = max(0, min(100, visual_status))
        
        # Redondear a entero para visualización limpia
        visual_status = int(round(visual_status))
        
        # 🔍 LOG DE DEBUGGING para diagnóstico
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"[VISUAL_STATUS] Usuario: {user.username}")
        logger.info(f"[VISUAL_STATUS] Actividad reciente (24h): {has_recent_activity}")
        logger.info(f"[VISUAL_STATUS] Alertas críticas: {critical_alerts}")
        logger.info(f"[VISUAL_STATUS] Alertas advertencia: {warning_alerts}")
        logger.info(f"[VISUAL_STATUS] Descansos hoy: {breaks_today}")
        logger.info(f"[VISUAL_STATUS] EAR promedio: {avg_ear_recent:.3f}")
        logger.info(f"[VISUAL_STATUS] Tasa parpadeo: {recent_blink_rate:.1f} parp/min")
        logger.info(f"[VISUAL_STATUS] Minutos activos hoy: {active_minutes_today:.1f}")
        logger.info(f"[VISUAL_STATUS] ✅ RESULTADO FINAL: {visual_status}%")

        # ================================================================
        # ETIQUETAS Y NIVELES DE ESTADO VISUAL
        # ================================================================
        # Determinar etiqueta, color y nivel basado en el puntaje
        if visual_status >= 85:
            visual_state_label = 'Óptimo'
            visual_state_level = 'green'
            visual_state_color = '#7CA982'  # Verde salud
        elif visual_status >= 70:
            visual_state_label = 'Muy Bueno'
            visual_state_level = 'light-green'
            visual_state_color = '#9BC17D'  # Verde claro
        elif visual_status >= 55:
            visual_state_label = 'Aceptable'
            visual_state_level = 'amber'
            visual_state_color = '#E8B86D'  # Ámbar
        elif visual_status >= 40:
            visual_state_label = 'Precaución'
            visual_state_level = 'orange'
            visual_state_color = '#E89E5F'  # Naranja
        else:
            visual_state_label = 'Fatiga Alta'
            visual_state_level = 'coral'
            visual_state_color = '#E07A5F'  # Coral/rojo
        
        # Datos para el gráfico de actividad visual (solo del día actual)
        chart_data = []
        chart_labels = []
        breaks_chart_data = []

        # Obtener la zona horaria del usuario (asumiendo campo user.timezone)
        import pytz
        user_tz = getattr(user, 'timezone', None)
        if user_tz:
            tz = pytz.timezone(user_tz)
        else:
            tz = timezone.get_current_timezone()

        # Definir el rango del día actual en la zona horaria del usuario
        local_now = timezone.localtime(timezone.now(), tz)
        start_of_today = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_today = start_of_today + timedelta(days=1)

        # Sesiones que solapan con el día actual (incluye en curso) para la gráfica
        chart_sessions = (
            MonitorSession.objects
            .filter(user=user)
            .filter(
                Q(start_time__lt=end_of_today),
                Q(end_time__gte=start_of_today) | Q(end_time__isnull=True)
            )
            .prefetch_related('pauses')
        )

        # Mostrar por hora local del usuario
        for hour in range(0, 24):
            hour_start = start_of_today + timedelta(hours=hour)
            hour_end = hour_start + timedelta(hours=1)

            # Promedio ponderado por minutos activos de parpadeos/min de las sesiones que solapan la hora
            weighted_sum = 0.0
            active_minutes_sum = 0.0
            for s in chart_sessions:
                # minutos activos de esta sesión dentro de la hora
                seconds_overlap = active_seconds_within(s, hour_start, hour_end)
                if seconds_overlap <= 0:
                    continue
                minutes_overlap = seconds_overlap / 60.0

                # tasa global de parpadeos de la sesión (parp/min)
                total_session_seconds = 0
                if getattr(s, 'effective_duration', None):
                    total_session_seconds = float(s.effective_duration or 0)
                if total_session_seconds <= 0:
                    if s.end_time:
                        total_session_seconds = float(s.calculate_active_duration())
                    else:
                        # sesión en curso: desde el inicio hasta ahora (menos pausas)
                        total_session_seconds = float(active_seconds_within(s, s.start_time, end_of_today))
                total_session_minutes = max(1e-6, total_session_seconds / 60.0)
                session_blink_rate = float(s.total_blinks or 0) / total_session_minutes

                weighted_sum += session_blink_rate * minutes_overlap
                active_minutes_sum += minutes_overlap

            blink_rate = round(weighted_sum / active_minutes_sum, 1) if active_minutes_sum > 0 else 0.0
            chart_data.append(blink_rate)
            chart_labels.append(f"{hour:02d}:00")

            # Descansos tomados por hora (pausas en sesiones con break_reminder)
            # Obtener sesiones que tuvieron break_reminder en esta hora
            sessions_with_breaks_in_hour = chart_sessions.filter(
                alerts__alert_type='break_reminder',
                alerts__triggered_at__gte=hour_start,
                alerts__triggered_at__lt=hour_end
            ).distinct()
            
            # Contar pausas en esas sesiones dentro de la hora
            hour_breaks = SessionPause.objects.filter(
                session__in=sessions_with_breaks_in_hour,
                pause_time__gte=hour_start,
                pause_time__lt=hour_end
            ).count()
            
            breaks_chart_data.append(hour_breaks)
        
        import json
        context.update({
            'total_hours': total_hours,
            'avg_blink_rate': avg_blink_rate,
            'completed_breaks': completed_breaks,
            'recommended_breaks': recommended_breaks,
            'visual_status': visual_status,
            'visual_state_label': visual_state_label,
            'visual_state_level': visual_state_level,
            'visual_state_color': visual_state_color,
            'chart_data': json.dumps(chart_data),
            'chart_labels': json.dumps(chart_labels),
            'breaks_chart_data': json.dumps(breaks_chart_data),
            # Métricas de diagnóstico para debugging (opcionales)
            'debug_critical_alerts': critical_alerts,
            'debug_warning_alerts': warning_alerts,
            'debug_avg_ear': round(avg_ear_recent, 3),
            'debug_recent_blink_rate': round(recent_blink_rate, 1),
            'debug_active_minutes_today': round(active_minutes_today, 1),
        })
        
        return context