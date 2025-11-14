from datetime import datetime, timedelta
import os
import csv
import io
import base64
import zipfile
import sys
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Sum, Count, Avg
from django.db.models.functions import TruncDate
from django.http import JsonResponse, HttpResponse
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.template.loader import render_to_string
from django.conf import settings

from apps.security.components.sidebar_menu_mixin import SidebarMenuMixin
from apps.monitoring.models import MonitorSession, AlertEvent
from apps.exercises.models import ExerciseSession

"""Vistas y exportación de reportes para VisionPulse OPTIMIZADO para velocidad."""


def _prepare_weasyprint_windows_dll_search():
    """En Windows, añade rutas candidatas de DLL para GTK+/Pango/Cairo."""
    if not sys.platform.startswith('win'):
        return
    if not hasattr(os, 'add_dll_directory'):
        pass

    dll_candidates = []

    try:
        extra = getattr(settings, 'WEASYPRINT_DLL_DIR', None)
        if extra:
            dll_candidates.append(extra)
        extra_list = getattr(settings, 'WEASYPRINT_DLL_DIRS', None)
        if extra_list:
            if isinstance(extra_list, (list, tuple)):
                dll_candidates.extend(list(extra_list))
            else:
                dll_candidates.append(str(extra_list))
    except Exception:
        pass

    env_root = os.environ.get('MSYS2_ROOT') or os.environ.get('MSYS2_PATH')
    gtk_bin = os.environ.get('GTK_BIN_DIR') or os.environ.get('WEASYPRINT_DLL_DIR')
    if env_root:
        dll_candidates.append(os.path.join(env_root, 'mingw64', 'bin'))
        dll_candidates.append(os.path.join(env_root, 'ucrt64', 'bin'))
    if gtk_bin:
        dll_candidates.append(gtk_bin)

    dll_candidates.extend([
        r'C:\\msys64\\mingw64\\bin',
        r'C:\\msys64\\ucrt64\\bin',
        r'C:\\Program Files\\GTK3-Runtime Win64\\bin',
    ])

    for p in dll_candidates:
        if p and os.path.isdir(p):
            try:
                if hasattr(os, 'add_dll_directory'):
                    os.add_dll_directory(p)
                if p not in os.environ.get('PATH', ''):
                    os.environ['PATH'] = p + os.pathsep + os.environ.get('PATH', '')
            except Exception:
                pass


def _generate_minimal_charts(fatigue_chart, screen_time_chart, distribution_chart):
    """
    Genera gráficas MINIMALISTAS y RÁPIDAS (DPI 80, sin efectos).
    Objetivo: reducir tiempo de generación manteniendo buena calidad visual
    """
    charts = {}
    
    # Configuración minimalista
    plt.rcParams['font.size'] = 8
    plt.rcParams['font.family'] = 'sans-serif'
    plt.rcParams['figure.dpi'] = 80  # DPI balanceado: velocidad + calidad
    
    # === 1. GRÁFICA DE FATIGA (línea simple) ===
    fig, ax = plt.subplots(figsize=(5, 2.5), facecolor='white')
    
    labels = fatigue_chart['labels']
    data = fatigue_chart['data']
    
    # Simplificar datos si hay muchos puntos
    if len(labels) > 12:
        step = len(labels) // 10
        labels = labels[::step]
        data = data[::step]
    
    x_positions = range(len(labels))
    x_labels = [l.split('-')[2] if '-' in l else l for l in labels]
    
    # Línea simple sin efectos
    ax.plot(x_positions, data, color='#666', linewidth=1.5, marker='o', markersize=3)
    
    # Estilo minimalista
    ax.set_ylim(0, 100)
    ax.set_xlim(-0.5, len(labels) - 0.5)
    ax.set_xticks(x_positions[::2])  # Menos etiquetas
    ax.set_xticklabels(x_labels[::2], fontsize=7)
    ax.set_yticks([0, 50, 100])
    ax.set_yticklabels(['0', '50', '100'], fontsize=7)
    ax.grid(axis='y', alpha=0.3, linestyle='-', linewidth=0.5)
    ax.set_ylabel('Índice de Fatiga', fontsize=8, color='#555')
    
    for spine in ax.spines.values():
        spine.set_visible(False)
    
    fig.tight_layout(pad=0.2)
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=80, bbox_inches='tight', pad_inches=0.05)
    plt.close(fig)
    buf.seek(0)
    charts['fatigue_img'] = 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode('utf-8')
    
    # === 2. GRÁFICA DE TIEMPO DE PANTALLA (barras simples) ===
    fig, ax = plt.subplots(figsize=(5, 2.5), facecolor='white')
    
    screen_labels = screen_time_chart['labels']
    screen_data = screen_time_chart['data']
    
    # Simplificar datos
    if len(screen_labels) > 12:
        step = len(screen_labels) // 10
        screen_labels = screen_labels[::step]
        screen_data = screen_data[::step]
    
    x_positions = range(len(screen_labels))
    x_labels = [l.split('-')[2] if '-' in l else l for l in screen_labels]
    
    # Barras simples sin gradientes
    ax.bar(x_positions, screen_data, color='#888', width=0.7, edgecolor='white', linewidth=0.5)
    
    # Styling minimalista
    ax.set_xticks(x_positions[::max(1, len(x_positions)//8)])
    ax.set_xticklabels([x_labels[i] for i in range(0, len(x_labels), max(1, len(x_labels)//8))], 
                       rotation=45, ha='right', fontsize=7)
    max_val = max(screen_data) if screen_data else 1
    ax.set_yticks([0, max_val//2, max_val] if max_val > 0 else [0])
    ax.tick_params(labelsize=7, colors='#666')
    ax.set_ylabel('Horas', fontsize=8, color='#555')
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_visible(False)
    ax.spines['bottom'].set_color('#ddd')
    
    plt.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=80, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    
    # NO PIL - directo a base64
    charts['screen_img'] = 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode('utf-8')
    
    # === 3. GRÁFICA DE DISTRIBUCIÓN (dona minimalista) ===
    fig, ax = plt.subplots(figsize=(3.5, 3.5), facecolor='white')
    
    dist_labels = distribution_chart['labels']
    dist_data = distribution_chart['data']
    colors_pie = ['#999', '#777', '#aaa']  # Grayscale
    
    # Dona simple
    wedges, texts, autotexts = ax.pie(
        dist_data, 
        colors=colors_pie, 
        autopct='%1.0f%%',
        startangle=90,
        pctdistance=0.82,
        wedgeprops=dict(width=0.4, edgecolor='white', linewidth=1),
        textprops=dict(color='#333', fontsize=7)
    )
    
    # Leyenda simple
    ax.legend(wedges, dist_labels, loc='center left', bbox_to_anchor=(1, 0, 0.5, 1), 
             fontsize=7, frameon=False)
    
    ax.axis('equal')
    
    plt.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=80, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    
    # NO PIL - directo a base64
    charts['alerts_img'] = 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode('utf-8')
    
    return charts


def _get_clean_filename(period, format_ext):
    """Genera nombres de archivo limpios y descriptivos."""
    now = timezone.localtime()
    date_str = now.strftime('%Y-%m-%d')
    time_str = now.strftime('%H-%M')
    
    period_names = {
        'today': 'hoy',
        'week': 'semanal',
        'month': 'mensual',
        'quarter': 'trimestral',
    }
    
    period_label = period_names.get(period, period)
    
    return f'visionpulse_reporte_{period_label}_{date_str}_{time_str}.{format_ext}'


class ReportListView(LoginRequiredMixin, SidebarMenuMixin, TemplateView):
    """Vista de lista histórica de reportes."""
    template_name = 'reports/report_list.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['section'] = 'reports'
        context['period'] = self.request.GET.get('period', 'month')
        context['reports'] = self.get_reports(context['period'])
        return context

    def get_reports(self, period):
        user = self.request.user
        now = timezone.localtime()
        today = now.date()
        if period == 'week':
            start = today - timedelta(days=6)
        elif period == 'month':
            start = today - timedelta(days=29)
        elif period == 'quarter':
            start = today - timedelta(days=89)
        else:
            start = today - timedelta(days=29)
        end = today
        sessions = MonitorSession.objects.filter(user=user, start_time__date__gte=start, start_time__date__lte=end)
        exercises = ExerciseSession.objects.filter(user=user, started_at__date__gte=start, started_at__date__lte=end)
        report = {
            'title': 'Reporte Mensual',
            'period': start.strftime('%B %Y'),
            'screen_time': sum([s.effective_duration or 0 for s in sessions]) / 3600.0,
            'exercises_completed': exercises.filter(completed=True).count(),
            'pauses_pct': self.get_pauses_pct(sessions),
        }
        return [report]

    def get_pauses_pct(self, sessions):
        total_sessions = sessions.count()
        if not total_sessions:
            return 0
        paused_sessions = sessions.filter(pauses__isnull=False).distinct().count()
        return int((paused_sessions / total_sessions) * 100)


@method_decorator(csrf_exempt, name='dispatch')
class ReportListDataView(LoginRequiredMixin, View):
    def get(self, request):
        period = request.GET.get('period', 'month')
        user = request.user
        now = timezone.localtime()
        today = now.date()
        if period == 'week':
            start = today - timedelta(days=6)
        elif period == 'month':
            start = today - timedelta(days=29)
        elif period == 'quarter':
            start = today - timedelta(days=89)
        else:
            start = today - timedelta(days=29)
        end = today
        sessions = MonitorSession.objects.filter(user=user, start_time__date__gte=start, start_time__date__lte=end)
        exercises = ExerciseSession.objects.filter(user=user, started_at__date__gte=start, started_at__date__lte=end)
        report = {
            'title': 'Reporte Mensual',
            'period': start.strftime('%B %Y'),
            'screen_time': round(sum([s.effective_duration or 0 for s in sessions]) / 3600.0, 1),
            'exercises_completed': exercises.filter(completed=True).count(),
            'pauses_pct': self.get_pauses_pct(sessions),
        }
        return JsonResponse({'status': 'success', 'reports': [report]})

    def get_pauses_pct(self, sessions):
        total_sessions = sessions.count()
        if not total_sessions:
            return 0
        paused_sessions = sessions.filter(pauses__isnull=False).distinct().count()
        return int((paused_sessions / total_sessions) * 100)

    def post(self, request):
        export_format = request.POST.get('format', 'csv')
        period = request.POST.get('period', 'month')
        user = request.user
        now = timezone.localtime()
        today = now.date()
        if period == 'week':
            start = today - timedelta(days=6)
        elif period == 'month':
            start = today - timedelta(days=29)
        elif period == 'quarter':
            start = today - timedelta(days=89)
        else:
            start = today - timedelta(days=29)
        end = today
        sessions = MonitorSession.objects.filter(user=user, start_time__date__gte=start, start_time__date__lte=end)
        exercises = ExerciseSession.objects.filter(user=user, started_at__date__gte=start, started_at__date__lte=end)
        
        if export_format == 'csv':
            response = HttpResponse(content_type='text/csv; charset=utf-8')
            filename = _get_clean_filename(period, 'csv')
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            response.write('\ufeff')  # UTF-8 BOM para Excel
            writer = csv.writer(response)
            writer.writerow(['Periodo', 'Tiempo de pantalla (h)', 'Ejercicios completados', 'Pausas (%)'])
            writer.writerow([
                start.strftime('%B %Y'),
                round(sum([s.effective_duration or 0 for s in sessions]) / 3600.0, 1),
                exercises.filter(completed=True).count(),
                self.get_pauses_pct(sessions)
            ])
            return response
        
        return JsonResponse({'status': 'error', 'message': 'Formato no soportado'}, status=400)


class DashboardView(LoginRequiredMixin, SidebarMenuMixin, TemplateView):
    """Renderiza el dashboard de Reportes y Estadísticas."""
    template_name = 'reports/dashboard.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update({
            'section': 'reports',
            'page_title': 'Reportes y Estadísticas',
        })
        return ctx


class ReportDataView(LoginRequiredMixin, View):
    """API JSON para datos del dashboard."""
    
    def get(self, request):
        try:
            period = request.GET.get('period', 'today')
            start_param = request.GET.get('start_date')
            end_param = request.GET.get('end_date')
            start_dt, end_dt, prev_start_dt, prev_end_dt = self._get_date_ranges(period, start_param, end_param)

            user = request.user

            sessions_qs = MonitorSession.objects.filter(user=user, start_time__date__gte=start_dt.date(), start_time__date__lte=end_dt.date())
            alerts_qs = AlertEvent.objects.filter(session__user=user, triggered_at__date__gte=start_dt.date(), triggered_at__date__lte=end_dt.date())
            exercises_qs = ExerciseSession.objects.filter(user=user, started_at__date__gte=start_dt.date(), started_at__date__lte=end_dt.date())

            prev_sessions_qs = MonitorSession.objects.filter(user=user, start_time__date__gte=prev_start_dt.date(), start_time__date__lte=prev_end_dt.date())
            prev_alerts_qs = AlertEvent.objects.filter(session__user=user, triggered_at__date__gte=prev_start_dt.date(), triggered_at__date__lte=prev_end_dt.date())
            prev_exercises_qs = ExerciseSession.objects.filter(user=user, started_at__date__gte=prev_start_dt.date(), started_at__date__lte=prev_end_dt.date())

            fatigue_chart = self._get_fatigue_evolution(sessions_qs, alerts_qs, start_dt, end_dt, period)
            data = {
                'summary': self._get_summary(sessions_qs, alerts_qs, exercises_qs, prev_sessions_qs, prev_alerts_qs, prev_exercises_qs, start_dt, end_dt, prev_start_dt, prev_end_dt, fatigue_chart, period),
                'fatigue_chart': fatigue_chart,
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
            # Última semana: últimos 7 días (hoy - 6 días hasta hoy)
            start = datetime.combine(today - timedelta(days=6), datetime.min.time(), tzinfo=now.tzinfo)
            end = datetime.combine(today, datetime.max.time(), tzinfo=now.tzinfo)
            # Semana anterior: 7 días antes (hoy - 13 días hasta hoy - 7 días)
            prev_start = datetime.combine(today - timedelta(days=13), datetime.min.time(), tzinfo=now.tzinfo)
            prev_end = datetime.combine(today - timedelta(days=7), datetime.max.time(), tzinfo=now.tzinfo)
        elif period == 'month':
            # Último mes: últimos 30 días (hoy - 29 días hasta hoy)
            start = datetime.combine(today - timedelta(days=29), datetime.min.time(), tzinfo=now.tzinfo)
            end = datetime.combine(today, datetime.max.time(), tzinfo=now.tzinfo)
            # Mes anterior: 30 días antes (hoy - 59 días hasta hoy - 30 días)
            prev_start = datetime.combine(today - timedelta(days=59), datetime.min.time(), tzinfo=now.tzinfo)
            prev_end = datetime.combine(today - timedelta(days=30), datetime.max.time(), tzinfo=now.tzinfo)
        elif period == 'quarter':
            # Últimos 3 meses: últimos 90 días (hoy - 89 días hasta hoy)
            start = datetime.combine(today - timedelta(days=89), datetime.min.time(), tzinfo=now.tzinfo)
            end = datetime.combine(today, datetime.max.time(), tzinfo=now.tzinfo)
            # 3 meses anteriores: 90 días antes (hoy - 179 días hasta hoy - 90 días)
            prev_start = datetime.combine(today - timedelta(days=179), datetime.min.time(), tzinfo=now.tzinfo)
            prev_end = datetime.combine(today - timedelta(days=90), datetime.max.time(), tzinfo=now.tzinfo)
        else:
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

    def _compute_active_seconds_in_range(self, session: MonitorSession, range_start: datetime, range_end: datetime) -> int:
        sess_start = session.start_time
        sess_end = session.end_time or timezone.localtime()

        window_start = max(range_start, sess_start)
        window_end = min(range_end, sess_end)
        if window_end <= window_start:
            return 0

        total_overlap = (window_end - window_start).total_seconds()

        paused_seconds = 0.0
        for p in session.pauses.all():
            p_start = p.pause_time
            p_end = p.resume_time or sess_end
            overlap_start = max(window_start, p_start)
            overlap_end = min(window_end, p_end)
            if overlap_end > overlap_start:
                paused_seconds += (overlap_end - overlap_start).total_seconds()

        active_seconds = max(0.0, total_overlap - paused_seconds)
        return int(active_seconds)

    def _sum_active_hours_period(self, sessions_qs, start_dt: datetime, end_dt: datetime) -> float:
        total_seconds = 0
        for s in sessions_qs.select_related('user').prefetch_related('pauses'):
            total_seconds += self._compute_active_seconds_in_range(s, start_dt, end_dt)
        return round(total_seconds / 3600.0, 1)

    def _pct_change(self, current: float, previous: float) -> float:
        """
        Calcula el porcentaje de cambio entre dos valores.
        
        Casos especiales:
        - previous = 0, current = 0 → 0.0 (sin datos)
        - previous = 0, current > 0 → 100.0 (representa aparición desde cero)
        - previous > 0, current = 0 → -100.0 (representa desaparición total)
        - previous = current → 0.0 (sin cambio)
        """
        # Ambos son cero: sin cambio
        if not previous and not current:
            return 0.0
        
        # Período anterior era cero pero ahora hay datos: representa nuevo incremento
        if not previous and current > 0:
            return 100.0  # Representa aparición/crecimiento desde cero
        
        # Período anterior tenía datos pero ahora es cero: caída total
        if previous > 0 and not current:
            return -100.0
        
        # Cálculo normal de porcentaje
        try:
            return round(((current - previous) / previous) * 100.0, 1)
        except ZeroDivisionError:
            return 0.0

    def _get_summary(self, sessions_qs, alerts_qs, exercises_qs, prev_sessions_qs, prev_alerts_qs, prev_exercises_qs, start_dt, end_dt, prev_start_dt, prev_end_dt, fatigue_chart=None, period='week'):
        screen_hours = self._sum_active_hours_period(sessions_qs, start_dt, end_dt)
        screen_hours_prev = self._sum_active_hours_period(prev_sessions_qs, prev_start_dt, prev_end_dt)

        sessions_count = sessions_qs.count()
        sessions_count_prev = prev_sessions_qs.count()

        alerts_count = alerts_qs.count()
        alerts_count_prev = prev_alerts_qs.count()

        exercises_count = exercises_qs.filter(completed=True).count()
        exercises_count_prev = prev_exercises_qs.filter(completed=True).count()

        vs_label = 'Sin datos'
        vs_level = 'amber'
        vs_score = 0.0
        if fatigue_chart and fatigue_chart.get('data'):
            last_idx = float(fatigue_chart['data'][-1])
            vs_score = max(0.0, min(100.0, 100.0 - last_idx))
            if vs_score >= 80:
                vs_label = 'Óptimo'
                vs_level = 'green'
            elif vs_score >= 50:
                vs_label = 'Aceptable'
                vs_level = 'amber'
            else:
                vs_label = 'Fatiga Alta'
                vs_level = 'coral'

        return {
            'screen_time': f"{int(screen_hours)}h",
            'screen_time_trend': self._pct_change(screen_hours, screen_hours_prev),
            'period': period,  # Período actual para etiquetas dinámicas
            'alerts': alerts_count,
            'alerts_trend': self._pct_change(alerts_count, alerts_count_prev),  # Cambiado a porcentaje para consistencia
            'exercises': exercises_count,
            'exercises_trend': self._pct_change(exercises_count, exercises_count_prev),
            'sessions': sessions_count,
            'sessions_trend': self._pct_change(sessions_count, sessions_count_prev),
            'visual_state_label': vs_label,
            'visual_state_level': vs_level,
            'visual_state_score': round(vs_score, 1),
        }

    def _date_range_labels(self, start_dt, end_dt):
        days = (end_dt.date() - start_dt.date()).days + 1
        labels = []
        for i in range(days):
            d = start_dt.date() + timedelta(days=i)
            labels.append(d.strftime('%Y-%m-%d'))
        return labels

    def _get_screen_time(self, sessions_qs, start_dt, end_dt):
        sessions = list(sessions_qs.select_related('user').prefetch_related('pauses'))
        labels = self._date_range_labels(start_dt, end_dt)
        hours = []
        for i, label in enumerate(labels):
            day_date = datetime.strptime(label, '%Y-%m-%d').date()
            day_start = datetime.combine(day_date, datetime.min.time(), tzinfo=start_dt.tzinfo)
            day_end = datetime.combine(day_date, datetime.max.time(), tzinfo=end_dt.tzinfo)
            day_seconds = 0
            for s in sessions:
                sess_start = s.start_time
                sess_end = s.end_time or timezone.localtime()
                if sess_end < day_start or sess_start > day_end:
                    continue
                day_seconds += self._compute_active_seconds_in_range(s, day_start, day_end)
            hours.append(round(day_seconds / 3600.0, 1))

        avg = round(sum(hours) / len(hours), 1) if hours else 0
        return {
            'labels': labels,
            'data': hours,
            'average': avg,
        }

    def _get_fatigue_evolution(self, sessions_qs, alerts_qs, start_dt, end_dt, period='today'):
        labels = self._date_range_labels(start_dt, end_dt)
        sessions = list(sessions_qs.select_related('user').prefetch_related('pauses'))

        def alerts_count_by_day(qs):
            rows = qs.annotate(day=TruncDate('triggered_at')).values('day').annotate(cnt=Count('id'))
            return {r['day'].strftime('%Y-%m-%d'): r['cnt'] for r in rows}

        fatigue_map = alerts_count_by_day(alerts_qs.filter(alert_type__in=[
            AlertEvent.ALERT_FATIGUE, AlertEvent.ALERT_MICROSLEEP
        ]))
        low_blink_map = alerts_count_by_day(alerts_qs.filter(alert_type=AlertEvent.ALERT_LOW_BLINK_RATE))
        distract_map = alerts_count_by_day(alerts_qs.filter(alert_type__in=[
            AlertEvent.ALERT_DISTRACT, AlertEvent.ALERT_FREQUENT_DISTRACT
        ]))

        data = []
        for label in labels:
            day_date = datetime.strptime(label, '%Y-%m-%d').date()
            day_start = datetime.combine(day_date, datetime.min.time(), tzinfo=start_dt.tzinfo)
            day_end = datetime.combine(day_date, datetime.max.time(), tzinfo=end_dt.tzinfo)

            weighted_focus_sum = 0.0
            active_seconds_sum = 0.0
            for s in sessions:
                sess_start = s.start_time
                sess_end = s.end_time or timezone.localtime()
                if sess_end < day_start or sess_start > day_end:
                    continue
                seconds = self._compute_active_seconds_in_range(s, day_start, day_end)
                if seconds <= 0:
                    continue
                focus_val = None
                if s.avg_focus_score is not None:
                    focus_val = s.avg_focus_score
                elif s.focus_percent is not None:
                    focus_val = s.focus_percent
                elif s.focus_score is not None:
                    focus_val = s.focus_score
                if focus_val is None:
                    continue
                focus_val = max(0.0, min(100.0, float(focus_val)))
                weighted_focus_sum += focus_val * seconds
                active_seconds_sum += seconds

            focus_avg = (weighted_focus_sum / active_seconds_sum) if active_seconds_sum > 0 else 100.0
            base = max(0.0, 100.0 - focus_avg)

            f_cnt = fatigue_map.get(label, 0)
            lb_cnt = low_blink_map.get(label, 0)
            d_cnt = distract_map.get(label, 0)
            penalty = 8 * f_cnt + 3 * lb_cnt + 2 * d_cnt
            idx = max(0.0, min(100.0, 0.6 * base + penalty))
            data.append(round(idx, 1))

        if period == 'quarter':
            grouped_labels = []
            grouped_data = []
            for i in range(0, len(labels), 7):
                week_labels = labels[i:i+7]
                week_data = data[i:i+7]
                if week_data:
                    grouped_labels.append(week_labels[0])
                    grouped_data.append(round(sum(week_data) / len(week_data), 1))
            return {
                'labels': grouped_labels,
                'data': grouped_data,
            }

        return {
            'labels': labels,
            'data': data,
        }

    def _get_distribution(self, sessions_qs, alerts_qs):
        """
        Obtiene la distribución de TODAS las alertas del usuario.
        Agrupa por tipo de alerta y cuenta cuántas veces ocurrió cada una.
        """
        # Obtener distribución de alertas por tipo
        alert_distribution = (
            alerts_qs
            .values('alert_type')
            .annotate(count=Count('id'))
            .order_by('-count')
        )
        
        # Si no hay alertas, retornar vacío
        if not alert_distribution:
            return {
                'labels': ['Sin alertas'],
                'data': [sessions_qs.count()],
            }
        
        # Mapear a nombres cortos y concisos
        short_labels = {
            'fatigue': 'Fatiga',
            'distract': 'Distracción',
            'low_light': 'Luz baja',
            'microsleep': 'Microsueño',
            'low_blink_rate': 'Parpadeo bajo',
            'high_blink_rate': 'Parpadeo alto',
            'frequent_distract': 'Distrac. frecuente',
            'phone_use': 'Uso celular',
            'postural_rigidity': 'Rigidez postural',
            'head_agitation': 'Mov. cabeza',
            'driver_absent': 'Ausente',
            'multiple_people': 'Múltiples personas',
            'camera_occluded': 'Cámara obstruida',
            'camera_lost': 'Cámara perdida',
            'head_tension': 'Tensión cuello',
            'micro_rhythm': 'Somnolencia',
            'bad_posture': 'Mala postura',
            'bad_distance': 'Dist. incorrecta',
            'strong_glare': 'Reflejo',
            'strong_light': 'Luz excesiva',
            'break_reminder': 'Descansos',
        }
        
        # Calcular el total para filtrar por porcentaje
        total_alerts = sum(item['count'] for item in alert_distribution)
        
        # Preparar labels y data para el gráfico
        labels = []
        data = []
        
        for item in alert_distribution[:10]:  # Limitamos a las top 10 alertas más frecuentes
            alert_type = item['alert_type']
            count = item['count']
            
            # Filtrar alertas que tengan al menos 1% del total
            percentage = (count / total_alerts * 100) if total_alerts > 0 else 0
            if percentage < 1.0:
                continue
            
            # Obtener el nombre corto de la alerta
            label = short_labels.get(alert_type, alert_type.replace('_', ' ').title())
            labels.append(label)
            data.append(count)
        
        return {
            'labels': labels,
            'data': data,
        }

    def _format_duration_hm(self, seconds: int) -> str:
        if not seconds:
            return '0h 0m'
        h = seconds // 3600
        m = (seconds % 3600) // 60
        return f"{h}h {m}m"

    def _get_sessions_list(self, sessions_qs):
        sessions = sessions_qs.select_related('user').prefetch_related('pauses').order_by('-start_time')[:100]
        items = []
        for s in sessions:
            if s.effective_duration and s.effective_duration > 0:
                duration_seconds = int(s.effective_duration)
            elif s.end_time:
                duration_seconds = s.calculate_active_duration()
            else:
                duration_seconds = self._compute_active_seconds_in_range(
                    s, s.start_time, timezone.localtime()
                )
            minutes = max(1, int(duration_seconds / 60)) if duration_seconds else 0
            blinks_per_min = 0
            if minutes:
                blinks_per_min = round((s.total_blinks or 0) / minutes)
            if s.avg_focus_score is not None:
                focus = s.avg_focus_score
            elif s.focus_percent is not None:
                focus = s.focus_percent
            else:
                focus = s.focus_score or 0
            alerts = getattr(s, 'total_alerts', None)
            if alerts is None or alerts == 0:
                alerts = s.alerts.count()
            items.append({
                'id': s.id,
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
                'description': a.description,
                'status': status,
            })
        return items


class ExportReportView(LoginRequiredMixin, View):
    """Genera y descarga reportes en PDF, Excel o CSV con diseño mejorado."""
    
    def post(self, request):
        fmt = (request.POST.get('format', 'pdf') or 'pdf').lower()
        period = request.POST.get('period', 'week')
        include_sessions = bool(request.POST.get('include_sessions'))
        include_alerts = bool(request.POST.get('include_alerts'))
        include_exercises = bool(request.POST.get('include_exercises'))
        include_charts = bool(request.POST.get('include_charts'))

        start_dt, end_dt, _, _ = ReportDataView()._get_date_ranges(period, None, None)
        user = request.user

        sessions_qs = MonitorSession.objects.filter(user=user, start_time__date__gte=start_dt.date(), start_time__date__lte=end_dt.date())
        alerts_qs = AlertEvent.objects.filter(session__user=user, triggered_at__date__gte=start_dt.date(), triggered_at__date__lte=end_dt.date())
        exercises_qs = ExerciseSession.objects.filter(user=user, started_at__date__gte=start_dt.date(), started_at__date__lte=end_dt.date())

        helper = ReportDataView()
        fatigue_chart = helper._get_fatigue_evolution(sessions_qs, alerts_qs, start_dt, end_dt, period)
        screen_time_chart = helper._get_screen_time(sessions_qs, start_dt, end_dt)
        distribution_chart = helper._get_distribution(sessions_qs, alerts_qs)

        sessions_list = []
        if include_sessions:
            sessions_list = helper._get_sessions_list(sessions_qs)
        
        alerts_list = helper._get_alerts_list(alerts_qs) if include_alerts else []
        
        exercises_list = []
        if include_exercises:
            for e in exercises_qs.order_by('-started_at')[:200]:
                exercises_list.append({
                    'title': getattr(e.exercise, 'title', 'Ejercicio'),
                    'date': timezone.localtime(e.started_at).strftime('%Y-%m-%d %H:%M'),
                    'completed': bool(e.completed),
                    'duration_min': int((e.duration or 0) / 60) if getattr(e, 'duration', None) else None,
                })

        # === EXPORTACIÓN CSV ===
        if fmt == 'csv':
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
                # Resumen General
                summary_io = io.StringIO()
                sw = csv.writer(summary_io, delimiter=';', quoting=csv.QUOTE_MINIMAL)
                sw.writerow(['═══════════════════════════════════════════════'])
                sw.writerow(['REPORTE VISIONPULSE - RESUMEN GENERAL'])
                sw.writerow(['═══════════════════════════════════════════════'])
                sw.writerow([])
                sw.writerow(['INFORMACIÓN DEL PERÍODO'])
                sw.writerow(['─────────────────────────────────────────────'])
                sw.writerow(['Período', period.upper()])
                sw.writerow(['Fecha de inicio', start_dt.strftime('%d/%m/%Y')])
                sw.writerow(['Fecha de fin', end_dt.strftime('%d/%m/%Y')])
                sw.writerow(['Generado el', timezone.localtime().strftime('%d/%m/%Y a las %H:%M:%S')])
                sw.writerow([])
                sw.writerow(['ESTADÍSTICAS DEL PERÍODO'])
                sw.writerow(['─────────────────────────────────────────────'])
                sw.writerow(['Concepto', 'Valor'])
                sw.writerow(['Tiempo promedio de pantalla por día', f"{screen_time_chart.get('average', 0):.1f} horas"])
                sw.writerow(['Total de sesiones monitoreadas', len(sessions_list)])
                sw.writerow(['Total de alertas generadas', len(alerts_list)])
                sw.writerow(['Ejercicios completados', sum(1 for e in exercises_list if e['completed'])])
                sw.writerow(['Ejercicios pendientes', sum(1 for e in exercises_list if not e['completed'])])
                sw.writerow([])
                sw.writerow(['═══════════════════════════════════════════════'])
                sw.writerow(['Fin del Resumen'])
                zf.writestr('01_resumen_general.csv', '\ufeff' + summary_io.getvalue())

                # Sesiones de Monitoreo
                if include_sessions and sessions_list:
                    sio = io.StringIO()
                    w = csv.writer(sio, delimiter=';', quoting=csv.QUOTE_MINIMAL)
                    w.writerow(['═══════════════════════════════════════════════════════════════'])
                    w.writerow(['SESIONES DE MONITOREO - DETALLE COMPLETO'])
                    w.writerow(['═══════════════════════════════════════════════════════════════'])
                    w.writerow([])
                    w.writerow(['Fecha y Hora', 'Duración', 'Parpadeos/min', 'Foco Promedio', 'Alertas Generadas'])
                    w.writerow(['─────────────', '────────', '─────────────', '─────────────', '────────────────'])
                    for s in sessions_list:
                        w.writerow([
                            s['date'],
                            s['duration'],
                            s['blinks'],
                            s['focus'],
                            s['alerts']
                        ])
                    w.writerow([])
                    w.writerow(['─────────────────────────────────────────────────────────────'])
                    w.writerow([f'Total de sesiones: {len(sessions_list)}'])
                    zf.writestr('02_sesiones_monitoreo.csv', '\ufeff' + sio.getvalue())

                # Alertas Generadas
                if include_alerts and alerts_list:
                    aio = io.StringIO()
                    w = csv.writer(aio, delimiter=';', quoting=csv.QUOTE_MINIMAL)
                    w.writerow(['═══════════════════════════════════════════════════════════════'])
                    w.writerow(['ALERTAS GENERADAS - REGISTRO COMPLETO'])
                    w.writerow(['═══════════════════════════════════════════════════════════════'])
                    w.writerow([])
                    w.writerow(['Tipo de Alerta', 'Fecha y Hora', 'Descripción', 'Estado'])
                    w.writerow(['──────────────', '─────────────', '───────────', '──────'])
                    for a in alerts_list:
                        w.writerow([
                            a['type'],
                            a['date'],
                            (a.get('description', '') or 'Sin descripción').replace('\n', ' ').replace('\r', ''),
                            a['status']
                        ])
                    w.writerow([])
                    w.writerow(['─────────────────────────────────────────────────────────────'])
                    resueltas = sum(1 for a in alerts_list if a['status'] == 'Resuelto')
                    pendientes = len(alerts_list) - resueltas
                    w.writerow([f'Total de alertas: {len(alerts_list)} (Resueltas: {resueltas}, Pendientes: {pendientes})'])
                    zf.writestr('03_alertas_generadas.csv', '\ufeff' + aio.getvalue())

                # Ejercicios Visuales
                if include_exercises and exercises_list:
                    eio = io.StringIO()
                    w = csv.writer(eio, delimiter=';', quoting=csv.QUOTE_MINIMAL)
                    w.writerow(['═══════════════════════════════════════════════════════════════'])
                    w.writerow(['EJERCICIOS VISUALES - HISTORIAL COMPLETO'])
                    w.writerow(['═══════════════════════════════════════════════════════════════'])
                    w.writerow([])
                    w.writerow(['Título del Ejercicio', 'Fecha de Realización', 'Estado', 'Duración (minutos)'])
                    w.writerow(['───────────────────', '────────────────────', '──────', '─────────────────'])
                    for ex in exercises_list:
                        w.writerow([
                            ex['title'],
                            ex['date'],
                            'Completado ✓' if ex['completed'] else 'Incompleto ✗',
                            ex.get('duration_min', 0)
                        ])
                    w.writerow([])
                    w.writerow(['─────────────────────────────────────────────────────────────'])
                    completados = sum(1 for e in exercises_list if e['completed'])
                    w.writerow([f'Total de ejercicios: {len(exercises_list)} (Completados: {completados}, Incompletos: {len(exercises_list) - completados})'])
                    zf.writestr('04_ejercicios_visuales.csv', '\ufeff' + eio.getvalue())

            buffer.seek(0)
            resp = HttpResponse(buffer.read(), content_type='application/zip')
            filename = _get_clean_filename(period, 'zip')
            resp['Content-Disposition'] = f'attachment; filename="{filename}"'
            return resp

        # === EXPORTACIÓN EXCEL ===
        if fmt == 'excel':
            try:
                import xlsxwriter
            except ImportError:
                return JsonResponse({'status': 'error', 'message': 'xlsxwriter no está instalado'}, status=500)
            
            output = io.BytesIO()
            with xlsxwriter.Workbook(output, {'in_memory': True}) as wb:
                # ═══ FORMATOS PROFESIONALES Y ELEGANTES ═══
                
                # Título principal (grande y destacado)
                title_fmt = wb.add_format({
                    'bold': True, 
                    'font_size': 18,
                    'font_name': 'Calibri',
                    'font_color': '#2C5F2D',
                    'bg_color': '#E8F5E9',
                    'align': 'center',
                    'valign': 'vcenter',
                    'border': 2,
                    'border_color': '#4CAF50'
                })
                
                # Subtítulos de sección
                section_fmt = wb.add_format({
                    'bold': True,
                    'font_size': 12,
                    'font_color': '#1B5E20',
                    'bg_color': '#C8E6C9',
                    'align': 'left',
                    'valign': 'vcenter',
                    'border': 1,
                    'border_color': '#81C784'
                })
                
                # Headers de tabla (columnas)
                header_fmt = wb.add_format({
                    'bold': True,
                    'font_size': 11,
                    'font_color': 'white',
                    'bg_color': '#43A047',
                    'border': 1,
                    'border_color': '#2E7D32',
                    'align': 'center',
                    'valign': 'vcenter',
                    'text_wrap': True
                })
                
                # Datos normales
                data_fmt = wb.add_format({
                    'font_size': 10,
                    'border': 1,
                    'border_color': '#C8E6C9',
                    'valign': 'vcenter'
                })
                
                # Datos centrados
                data_center_fmt = wb.add_format({
                    'font_size': 10,
                    'border': 1,
                    'border_color': '#C8E6C9',
                    'align': 'center',
                    'valign': 'vcenter'
                })
                
                # Números con decimales
                number_fmt = wb.add_format({
                    'font_size': 10,
                    'border': 1,
                    'border_color': '#C8E6C9',
                    'num_format': '#,##0.0',
                    'align': 'right',
                    'valign': 'vcenter'
                })
                
                # Números enteros
                integer_fmt = wb.add_format({
                    'font_size': 10,
                    'border': 1,
                    'border_color': '#C8E6C9',
                    'num_format': '#,##0',
                    'align': 'center',
                    'valign': 'vcenter'
                })
                
                # Fechas
                date_fmt = wb.add_format({
                    'font_size': 10,
                    'border': 1,
                    'border_color': '#C8E6C9',
                    'align': 'center',
                    'valign': 'vcenter'
                })
                
                # Etiquetas (para headers de resumen)
                label_fmt = wb.add_format({
                    'bold': True,
                    'font_size': 10,
                    'bg_color': '#F1F8E9',
                    'border': 1,
                    'border_color': '#C8E6C9',
                    'valign': 'vcenter'
                })
                
                # Valores de resumen
                value_fmt = wb.add_format({
                    'font_size': 10,
                    'font_color': '#1B5E20',
                    'bold': True,
                    'bg_color': 'white',
                    'border': 1,
                    'border_color': '#C8E6C9',
                    'align': 'right',
                    'valign': 'vcenter'
                })
                
                # Estado COMPLETADO (verde vibrante)
                success_fmt = wb.add_format({
                    'bg_color': '#4CAF50',
                    'font_color': 'white',
                    'bold': True,
                    'font_size': 10,
                    'border': 1,
                    'border_color': '#388E3C',
                    'align': 'center',
                    'valign': 'vcenter'
                })
                
                # Estado PENDIENTE/ALERTA (naranja/amarillo)
                warning_fmt = wb.add_format({
                    'bg_color': '#FF9800',
                    'font_color': 'white',
                    'bold': True,
                    'font_size': 10,
                    'border': 1,
                    'border_color': '#F57C00',
                    'align': 'center',
                    'valign': 'vcenter'
                })
                
                # Estado CRÍTICO (rojo)
                danger_fmt = wb.add_format({
                    'bg_color': '#F44336',
                    'font_color': 'white',
                    'bold': True,
                    'font_size': 10,
                    'border': 1,
                    'border_color': '#D32F2F',
                    'align': 'center',
                    'valign': 'vcenter'
                })

                # ═══ HOJA 1: RESUMEN EJECUTIVO ═══
                ws1 = wb.add_worksheet('📊 Resumen')
                ws1.set_column('A:A', 38)
                ws1.set_column('B:B', 22)
                ws1.set_row(0, 30)  # Altura del título
                
                # Título principal
                ws1.merge_range('A1:B1', '📊 REPORTE VISIONPULSE - RESUMEN EJECUTIVO', title_fmt)
                
                # Información del período
                ws1.write('A3', '📅 INFORMACIÓN DEL PERÍODO', section_fmt)
                ws1.write('B3', '', section_fmt)
                
                ws1.write('A4', 'Período:', label_fmt)
                ws1.write('B4', period.upper(), value_fmt)
                
                ws1.write('A5', 'Fecha de inicio:', label_fmt)
                ws1.write('B5', start_dt.strftime('%d/%m/%Y'), value_fmt)
                
                ws1.write('A6', 'Fecha de finalización:', label_fmt)
                ws1.write('B6', end_dt.strftime('%d/%m/%Y'), value_fmt)
                
                ws1.write('A7', 'Reporte generado:', label_fmt)
                ws1.write('B7', timezone.localtime().strftime('%d/%m/%Y a las %H:%M'), value_fmt)
                
                # Estadísticas principales
                ws1.write('A9', '📈 ESTADÍSTICAS GENERALES', section_fmt)
                ws1.write('B9', '', section_fmt)
                
                ws1.write('A10', 'Tiempo promedio de pantalla (horas/día):', label_fmt)
                ws1.write('B10', screen_time_chart.get('average', 0), number_fmt)
                
                ws1.write('A11', 'Total de sesiones monitoreadas:', label_fmt)
                ws1.write('B11', len(sessions_list), integer_fmt)
                
                ws1.write('A12', 'Total de alertas generadas:', label_fmt)
                alert_color = danger_fmt if len(alerts_list) > 10 else (warning_fmt if len(alerts_list) > 5 else success_fmt)
                ws1.write('B12', len(alerts_list), alert_color)
                
                ws1.write('A13', 'Ejercicios completados:', label_fmt)
                completed = sum(1 for e in exercises_list if e['completed'])
                ws1.write('B13', completed, success_fmt)
                
                ws1.write('A14', 'Ejercicios pendientes:', label_fmt)
                pending = len(exercises_list) - completed
                pending_color = warning_fmt if pending > 0 else success_fmt
                ws1.write('B14', pending, pending_color)

                # Gráficas en Excel si están incluidas
                if include_charts:
                    # Generar gráficas embebidas
                    row_offset = 15
                    
                    # Gráfica de fatiga
                    ws1.write(f'A{row_offset}', 'Evolución de Fatiga Visual', header_fmt)
                    chart1 = wb.add_chart({'type': 'line'})
                    # Escribir datos para la gráfica
                    ws1.write_row(f'D{row_offset+1}', ['Día'] + fatigue_chart['labels'][:10])
                    ws1.write_row(f'D{row_offset+2}', ['Índice'] + fatigue_chart['data'][:10])
                    chart1.add_series({
                        'name': 'Índice de Fatiga',
                        'categories': f'=\'📊 Resumen\'!$E${row_offset+1}:$N${row_offset+1}',
                        'values': f'=\'📊 Resumen\'!$E${row_offset+2}:$N${row_offset+2}',
                        'line': {'color': '#e88a85', 'width': 2.5},
                    })
                    chart1.set_title({'name': 'Evolución de Fatiga'})
                    chart1.set_size({'width': 480, 'height': 288})
                    ws1.insert_chart(f'A{row_offset+1}', chart1)

                # ═══ HOJA 2: SESIONES DE MONITOREO ═══
                if include_sessions and sessions_list:
                    ws2 = wb.add_worksheet('🖥️ Sesiones')
                    ws2.set_column('A:A', 20)
                    ws2.set_column('B:B', 14)
                    ws2.set_column('C:C', 16)
                    ws2.set_column('D:D', 17)
                    ws2.set_column('E:E', 14)
                    ws2.set_row(0, 30)
                    
                    # Título
                    ws2.merge_range('A1:E1', '🖥️ SESIONES DE MONITOREO - DETALLE COMPLETO', title_fmt)
                    
                    # Headers de columnas
                    headers = ['Fecha y Hora', 'Duración', 'Parpadeos/min', 'Foco Promedio', 'Alertas']
                    ws2.write_row('A3', headers, header_fmt)
                    ws2.set_row(2, 25)
                    
                    # Datos de sesiones
                    for row, s in enumerate(sessions_list, start=4):
                        ws2.write(f'A{row}', s['date'], date_fmt)
                        ws2.write(f'B{row}', s['duration'], data_center_fmt)
                        
                        # Parpadeos con formato condicional
                        blinks = s['blinks']
                        blink_fmt = success_fmt if blinks >= 15 else (warning_fmt if blinks >= 10 else danger_fmt)
                        ws2.write(f'C{row}', blinks, blink_fmt)
                        
                        # Foco con formato
                        ws2.write(f'D{row}', s['focus'], data_center_fmt)
                        
                        # Alertas con colores
                        alerts = s['alerts']
                        if alerts == 0:
                            alert_color = success_fmt
                        elif alerts <= 2:
                            alert_color = warning_fmt
                        else:
                            alert_color = danger_fmt
                        ws2.write(f'E{row}', alerts, alert_color)
                    
                    # Resumen final
                    final_row = len(sessions_list) + 5
                    ws2.merge_range(f'A{final_row}:B{final_row}', f'Total de sesiones: {len(sessions_list)}', section_fmt)

                # ═══ HOJA 3: ALERTAS GENERADAS ═══
                if include_alerts and alerts_list:
                    ws3 = wb.add_worksheet('⚠️ Alertas')
                    ws3.set_column('A:A', 22)
                    ws3.set_column('B:B', 20)
                    ws3.set_column('C:C', 45)
                    ws3.set_column('D:D', 15)
                    ws3.set_row(0, 30)
                    
                    # Título
                    ws3.merge_range('A1:D1', '⚠️ ALERTAS GENERADAS - REGISTRO COMPLETO', title_fmt)
                    
                    # Headers
                    headers = ['Tipo de Alerta', 'Fecha y Hora', 'Descripción Detallada', 'Estado']
                    ws3.write_row('A3', headers, header_fmt)
                    ws3.set_row(2, 25)
                    
                    # Datos de alertas
                    for row, a in enumerate(alerts_list, start=4):
                        # Tipo de alerta con color
                        alert_type = a['type']
                        if 'Fatiga' in alert_type:
                            type_fmt = danger_fmt
                        elif 'Distracción' in alert_type or 'Distract' in alert_type:
                            type_fmt = warning_fmt
                        else:
                            type_fmt = data_center_fmt
                        ws3.write(f'A{row}', alert_type, type_fmt)
                        
                        # Fecha
                        ws3.write(f'B{row}', a['date'], date_fmt)
                        
                        # Descripción con wrap
                        desc = (a.get('description', '') or 'Sin descripción disponible')
                        desc_fmt = wb.add_format({
                            'font_size': 10,
                            'border': 1,
                            'border_color': '#C8E6C9',
                            'valign': 'top',
                            'text_wrap': True
                        })
                        ws3.write(f'C{row}', desc, desc_fmt)
                        
                        # Estado
                        status_color = success_fmt if a['status'] == 'Resuelto' else danger_fmt
                        ws3.write(f'D{row}', a['status'], status_color)
                    
                    # Resumen
                    final_row = len(alerts_list) + 5
                    resueltas = sum(1 for a in alerts_list if a['status'] == 'Resuelto')
                    pendientes = len(alerts_list) - resueltas
                    ws3.merge_range(f'A{final_row}:D{final_row}', 
                        f'Total: {len(alerts_list)} alertas (✓ Resueltas: {resueltas} | ✗ Pendientes: {pendientes})', 
                        section_fmt)

                # ═══ HOJA 4: EJERCICIOS VISUALES ═══
                if include_exercises and exercises_list:
                    ws4 = wb.add_worksheet('💪 Ejercicios')
                    ws4.set_column('A:A', 40)
                    ws4.set_column('B:B', 20)
                    ws4.set_column('C:C', 18)
                    ws4.set_column('D:D', 18)
                    ws4.set_row(0, 30)
                    
                    # Título
                    ws4.merge_range('A1:D1', '💪 EJERCICIOS VISUALES - HISTORIAL COMPLETO', title_fmt)
                    
                    # Headers
                    headers = ['Título del Ejercicio', 'Fecha de Realización', 'Estado', 'Duración (minutos)']
                    ws4.write_row('A3', headers, header_fmt)
                    ws4.set_row(2, 25)
                    
                    # Datos de ejercicios
                    for row, ex in enumerate(exercises_list, start=4):
                        # Título
                        ws4.write(f'A{row}', ex['title'], data_fmt)
                        
                        # Fecha
                        ws4.write(f'B{row}', ex['date'], date_fmt)
                        
                        # Estado con íconos
                        if ex['completed']:
                            status_text = '✓ Completado'
                            status_color = success_fmt
                        else:
                            status_text = '✗ Incompleto'
                            status_color = danger_fmt
                        ws4.write(f'C{row}', status_text, status_color)
                        
                        # Duración
                        duration = ex.get('duration_min') or 0
                        ws4.write(f'D{row}', duration, integer_fmt)
                    
                    # Resumen final
                    final_row = len(exercises_list) + 5
                    completados = sum(1 for e in exercises_list if e['completed'])
                    incompletos = len(exercises_list) - completados
                    ws4.merge_range(f'A{final_row}:D{final_row}',
                        f'Total: {len(exercises_list)} ejercicios (✓ Completados: {completados} | ✗ Incompletos: {incompletos})',
                        section_fmt)

            output.seek(0)
            resp = HttpResponse(output.read(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            filename = _get_clean_filename(period, 'xlsx')
            resp['Content-Disposition'] = f'attachment; filename="{filename}"'
            return resp

        # === EXPORTACIÓN PDF ===
        charts = {}
        if include_charts:
            charts = _generate_minimal_charts(fatigue_chart, screen_time_chart, distribution_chart)

        # Cargar logo (preferir SVG por tamaño reducido)
        logo_base64 = None
        try:
            if settings.STATIC_ROOT:
                svg_path = os.path.join(settings.STATIC_ROOT, 'img', 'dashboard', 'logo.svg')
                png_path = os.path.join(settings.STATIC_ROOT, 'img', 'dashboard', 'logo.png')
            else:
                svg_path = os.path.join(settings.BASE_DIR, 'static', 'img', 'dashboard', 'logo.svg')
                png_path = os.path.join(settings.BASE_DIR, 'static', 'img', 'dashboard', 'logo.png')

            if os.path.exists(svg_path):
                with open(svg_path, 'rb') as f:
                    logo_base64 = 'data:image/svg+xml;base64,' + base64.b64encode(f.read()).decode('utf-8')
            elif os.path.exists(png_path):
                with open(png_path, 'rb') as f:
                    logo_base64 = 'data:image/png;base64,' + base64.b64encode(f.read()).decode('utf-8')
        except Exception:
            pass

        generated_at = timezone.localtime().strftime('%d/%m/%Y %H:%M:%S')

        period_label_map = {
            'today': 'hoy',
            'week': 'semanal',
            'month': 'mensual',
            'quarter': 'trimestral',
        }
        period_label_es = period_label_map.get(period, period)

        context = {
            'period_label': period,
            'period_label_es': period_label_es,
            'start_date': start_dt.strftime('%d/%m/%Y'),
            'end_date': end_dt.strftime('%d/%m/%Y'),
            'generated_at': generated_at,
            'logo_base64': logo_base64,
            'include_sessions': include_sessions,
            'include_alerts': include_alerts,
            'include_exercises': include_exercises,
            'include_charts': include_charts,
            'sessions': sessions_list,
            'alerts': alerts_list,
            'exercises': exercises_list,
            'charts': charts,
        }

        html = render_to_string('reports/export_report.html', context)
        pdf_io = io.BytesIO()
        
        try:
            _prepare_weasyprint_windows_dll_search()
            from weasyprint import HTML
            HTML(string=html, base_url=request.build_absolute_uri('/')).write_pdf(
                pdf_io,
                optimize_size=("fonts", "images"),
            )
            pdf_io.seek(0)
            resp = HttpResponse(pdf_io.read(), content_type='application/pdf')
            filename = _get_clean_filename(period, 'pdf')
            resp['Content-Disposition'] = f'attachment; filename="{filename}"'
            return resp
        except (ImportError, OSError) as e:
            attempted = []
            if sys.platform.startswith('win'):
                attempted = [
                    getattr(settings, 'WEASYPRINT_DLL_DIR', None),
                    os.environ.get('GTK_BIN_DIR'),
                    os.environ.get('WEASYPRINT_DLL_DIR'),
                    os.environ.get('MSYS2_ROOT'),
                    r'C:\\msys64\\mingw64\\bin',
                    r'C:\\msys64\\ucrt64\\bin',
                    r'C:\\Program Files\\GTK3-Runtime Win64\\bin',
                ]
            msg = (
                'Error al generar PDF con WeasyPrint: ' + str(e) + '\n' +
                'Requisitos en Windows: instalar MSYS2/GTK y apuntar a la carpeta bin vía '\
                'variable de entorno GTK_BIN_DIR o setting WEASYPRINT_DLL_DIR.\n' +
                f'Rutas probadas: {[p for p in attempted if p]}\n' +
                'Usa Excel/CSV mientras tanto.'
            )
            return HttpResponse(msg, status=500)