from datetime import datetime, timedelta

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Sum, Count, Avg
from django.db.models.functions import TruncDate
from django.http import JsonResponse
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from apps.security.components.sidebar_menu_mixin import SidebarMenuMixin
from apps.monitoring.models import MonitorSession, AlertEvent
from apps.exercises.models import ExerciseSession


class ReportListView(LoginRequiredMixin, SidebarMenuMixin, TemplateView):
    template_name = 'reports/report_list.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['section'] = 'reports'
        return context


class DashboardView(LoginRequiredMixin, SidebarMenuMixin, TemplateView):
    template_name = 'reports/dashboard.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update({
            'section': 'reports',
            'page_title': 'Reportes y Estadísticas',
        })
        return ctx


class ReportDataView(LoginRequiredMixin, View):
    def get(self, request):
        try:
            period = request.GET.get('period', 'today')
            start_param = request.GET.get('start_date')
            end_param = request.GET.get('end_date')
            start_dt, end_dt, prev_start_dt, prev_end_dt = self._get_date_ranges(period, start_param, end_param)

            user = request.user

            # Querysets
            sessions_qs = MonitorSession.objects.filter(user=user, start_time__date__gte=start_dt.date(), start_time__date__lte=end_dt.date())
            alerts_qs = AlertEvent.objects.filter(session__user=user, triggered_at__date__gte=start_dt.date(), triggered_at__date__lte=end_dt.date())
            exercises_qs = ExerciseSession.objects.filter(user=user, started_at__date__gte=start_dt.date(), started_at__date__lte=end_dt.date())

            # Previous period for trends
            prev_sessions_qs = MonitorSession.objects.filter(user=user, start_time__date__gte=prev_start_dt.date(), start_time__date__lte=prev_end_dt.date())
            prev_alerts_qs = AlertEvent.objects.filter(session__user=user, triggered_at__date__gte=prev_start_dt.date(), triggered_at__date__lte=prev_end_dt.date())
            prev_exercises_qs = ExerciseSession.objects.filter(user=user, started_at__date__gte=prev_start_dt.date(), started_at__date__lte=prev_end_dt.date())

            data = {
                'summary': self._get_summary(sessions_qs, alerts_qs, exercises_qs, prev_sessions_qs, prev_alerts_qs, prev_exercises_qs),
                'fatigue_chart': self._get_fatigue_evolution(sessions_qs, alerts_qs, start_dt, end_dt),
                'screen_time_chart': self._get_screen_time(sessions_qs, start_dt, end_dt),
                'distribution_chart': self._get_distribution(sessions_qs, alerts_qs),
                'sessions': self._get_sessions_list(sessions_qs),
                'alerts': self._get_alerts_list(alerts_qs),
            }

            return JsonResponse({'status': 'success', 'data': data})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

    def _get_date_ranges(self, period: str, start_date: str | None, end_date: str | None):
        now = timezone.localtime()
        today = now.date()

        if period == 'today':
            start = datetime.combine(today, datetime.min.time(), tzinfo=now.tzinfo)
            end = datetime.combine(today, datetime.max.time(), tzinfo=now.tzinfo)
            prev_start = start - timedelta(days=1)
            prev_end = end - timedelta(days=1)
        elif period == 'week':
            start = datetime.combine(today - timedelta(days=6), datetime.min.time(), tzinfo=now.tzinfo)
            end = datetime.combine(today, datetime.max.time(), tzinfo=now.tzinfo)
            prev_start = start - timedelta(days=7)
            prev_end = end - timedelta(days=7)
        elif period == 'month':
            start = datetime.combine(today - timedelta(days=29), datetime.min.time(), tzinfo=now.tzinfo)
            end = datetime.combine(today, datetime.max.time(), tzinfo=now.tzinfo)
            prev_start = start - timedelta(days=30)
            prev_end = end - timedelta(days=30)
        else:  # custom
            if not start_date or not end_date:
                raise ValueError('start_date and end_date are required for custom period')
            s = datetime.strptime(start_date, '%Y-%m-%d').date()
            e = datetime.strptime(end_date, '%Y-%m-%d').date()
            if s >= e:
                raise ValueError('start_date must be before end_date')
            start = datetime.combine(s, datetime.min.time(), tzinfo=now.tzinfo)
            end = datetime.combine(e, datetime.max.time(), tzinfo=now.tzinfo)
            delta = (end.date() - start.date()).days + 1
            prev_start = start - timedelta(days=delta)
            prev_end = end - timedelta(days=delta)

        return start, end, prev_start, prev_end

    def _safe_hours_sum(self, qs):
        # Try both duration fields and pick the larger meaningful sum
        sum_total = qs.aggregate(v=Sum('total_duration'))['v'] or 0
        sum_seconds = qs.aggregate(v=Sum('duration_seconds'))['v'] or 0
        seconds = int(sum_total or sum_seconds or 0)
        return round(seconds / 3600.0, 1)

    def _pct_change(self, current: float, previous: float) -> float:
        if not previous:
            return 0.0
        try:
            return round(((current - previous) / previous) * 100.0, 1)
        except ZeroDivisionError:
            return 0.0

    def _get_summary(self, sessions_qs, alerts_qs, exercises_qs, prev_sessions_qs, prev_alerts_qs, prev_exercises_qs):
        screen_hours = self._safe_hours_sum(sessions_qs)
        screen_hours_prev = self._safe_hours_sum(prev_sessions_qs)

        sessions_count = sessions_qs.count()
        sessions_count_prev = prev_sessions_qs.count()

        alerts_count = alerts_qs.count()
        alerts_count_prev = prev_alerts_qs.count()

        exercises_count = exercises_qs.filter(completed=True).count()
        exercises_count_prev = prev_exercises_qs.filter(completed=True).count()

        return {
            'screen_time': f"{int(screen_hours)}h",
            'screen_time_trend': self._pct_change(screen_hours, screen_hours_prev),
            'alerts': alerts_count,
            'alerts_trend': alerts_count - alerts_count_prev,
            'exercises': exercises_count,
            'exercises_trend': self._pct_change(exercises_count, exercises_count_prev),
            'sessions': sessions_count,
            'sessions_trend': self._pct_change(sessions_count, sessions_count_prev),
        }

    def _date_range_labels(self, start_dt, end_dt):
        days = (end_dt.date() - start_dt.date()).days + 1
        labels = []
        for i in range(days):
            d = start_dt.date() + timedelta(days=i)
            labels.append(d.strftime('%Y-%m-%d'))
        return labels

    def _get_screen_time(self, sessions_qs, start_dt, end_dt):
        by_day = sessions_qs.annotate(day=TruncDate('start_time')).values('day').annotate(
            total_seconds=Sum('duration_seconds'),
            total_duration=Sum('total_duration'),
        ).order_by('day')

        sec_by_day = {row['day'].strftime('%Y-%m-%d'): int((row['total_duration'] or 0) or (row['total_seconds'] or 0) or 0) for row in by_day}
        labels = self._date_range_labels(start_dt, end_dt)
        hours = [round((sec_by_day.get(label, 0) / 3600.0), 1) for label in labels]
        avg = round(sum(hours) / len(hours), 1) if hours else 0
        return {
            'labels': labels,
            'data': hours,
            'average': avg,
        }

    def _get_fatigue_evolution(self, sessions_qs, alerts_qs, start_dt, end_dt):
        # Build basic fatigue index per day = base 20 + 10 * alerts that day (capped 100)
        alerts_by_day = alerts_qs.annotate(day=TruncDate('triggered_at')).values('day').annotate(cnt=Count('id')).order_by('day')
        map_alerts = {row['day'].strftime('%Y-%m-%d'): row['cnt'] for row in alerts_by_day}
        labels = self._date_range_labels(start_dt, end_dt)
        data = [min(100, 20 + 10 * map_alerts.get(label, 0)) for label in labels]
        return {
            'labels': labels,
            'data': data,
        }

    def _get_distribution(self, sessions_qs, alerts_qs):
        distract = alerts_qs.filter(alert_type=AlertEvent.ALERT_DISTRACT).count()
        fatigue = alerts_qs.filter(alert_type=AlertEvent.ALERT_FATIGUE).count()
        # Sessions without any alerts in the period
        session_ids_with_alerts = alerts_qs.values_list('session_id', flat=True).distinct()
        no_alert_sessions = sessions_qs.exclude(id__in=session_ids_with_alerts).count()
        return {
            'labels': ['Distracción', 'Fatiga', 'Sin alerta'],
            'data': [distract, fatigue, no_alert_sessions],
        }

    def _format_duration_hm(self, seconds: int) -> str:
        if not seconds:
            return '0h 0m'
        h = seconds // 3600
        m = (seconds % 3600) // 60
        return f"{h}h {m}m"

    def _get_sessions_list(self, sessions_qs):
        sessions = sessions_qs.select_related('user').order_by('-start_time')[:100]
        items = []
        for s in sessions:
            duration_seconds = int(s.total_duration or s.duration_seconds or 0)
            minutes = max(1, int(duration_seconds / 60)) if duration_seconds else 0
            blinks_per_min = 0
            if minutes:
                blinks_per_min = round((s.total_blinks or 0) / minutes)
            focus = s.focus_percent if s.focus_percent is not None else (s.focus_score or 0)
            alerts = getattr(s, 'total_alerts', None)
            if alerts is None or alerts == 0:
                # fallback count from related manager
                alerts = s.alerts.count()
            items.append({
                'date': timezone.localtime(s.start_time).strftime('%Y-%m-%d %H:%M'),
                'duration': self._format_duration_hm(duration_seconds),
                'blinks': blinks_per_min,
                'focus': f"{round(focus or 0)}%",
                'alerts': alerts,
            })
        return items

    def _get_alerts_list(self, alerts_qs):
        items = []
        for a in alerts_qs.select_related('session').order_by('-triggered_at')[:100]:
            if a.alert_type == AlertEvent.ALERT_FATIGUE:
                type_label = 'Fatiga Visual'
            elif a.alert_type == AlertEvent.ALERT_DISTRACT:
                type_label = 'Distracción'
            else:
                type_label = a.get_alert_type_display()
            status = 'Resuelto' if a.resolved else 'Pendiente'
            items.append({
                'type': type_label,
                'date': timezone.localtime(a.triggered_at).strftime('%Y-%m-%d %H:%M'),
                'desc': a.description,
                'status': status,
            })
        return items
