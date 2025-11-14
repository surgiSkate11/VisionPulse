from apps.security.components.sidebar_menu_mixin import SidebarMenuMixin
from apps.security.components.mixin_crud import PermissionMixin
from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse
from apps.security.forms.configuration import ProfileForm, SettingsForm
from apps.monitoring.models import UserMonitoringConfig
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
from django.db.models import Count, Sum, Q, Value, FloatField, DecimalField, Func, F, Subquery, OuterRef
from django.db.models.functions import Cast, Coalesce, TruncDate
from django.core.cache import cache
from django.db.models import ExpressionWrapper
from apps.monitoring.models import MonitorSession, AlertEvent, SessionPause
from apps.exercises.models import ExerciseSession
import json

class ProfileView(SidebarMenuMixin, PermissionMixin, LoginRequiredMixin, TemplateView):
    template_name = 'core/profile.html'
    permission_required = 'view_user'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        context['form'] = ProfileForm(instance=user)
        return context

    def post(self, request, *args, **kwargs):
        user = request.user
        form = ProfileForm(request.POST, request.FILES, instance=user)
        if form.is_valid():
            form.save()
            
            # Si es una petición AJAX, devolver JSON con la configuración actualizada
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                from django.http import JsonResponse
                return JsonResponse({
                    'success': True,
                    'message': 'Tu perfil se ha actualizado correctamente.',
                    'audio_config': {
                        'notification_sound': user.notification_sound,
                        'notification_sound_enabled': user.notification_sound_enabled,
                        'alert_volume': float(user.alert_volume) if hasattr(user, 'alert_volume') else 0.7
                    }
                })
            
            messages.success(request, 'Tu perfil se ha actualizado correctamente.')
            return redirect(reverse('security:profile'))
        else:
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                from django.http import JsonResponse
                errors = {field: [str(e) for e in error_list] for field, error_list in form.errors.items()}
                return JsonResponse({
                    'success': False,
                    'message': 'Por favor corrige los errores del formulario.',
                    'errors': errors
                }, status=400)
            
            messages.error(request, 'Por favor corrige los errores del formulario.')
            context = self.get_context_data()
            context['form'] = form
            return self.render_to_response(context)

class UserSettingsView(SidebarMenuMixin, PermissionMixin, LoginRequiredMixin, TemplateView):
    template_name = 'core/settings.html'
    permission_required = 'change_user'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        config, _ = UserMonitoringConfig.objects.get_or_create(user=user)
        context['form'] = SettingsForm(instance=config)
        context['monitoring_config'] = config
        return context

    def post(self, request, *args, **kwargs):
        user = request.user
        config, _ = UserMonitoringConfig.objects.get_or_create(user=user)
        form = SettingsForm(request.POST, instance=config)
        if form.is_valid():
            form.save()
            messages.success(request, 'Configuraciones guardadas correctamente.')
            return redirect(reverse('security:user_settings'))
        else:
            messages.error(request, 'Revisa los campos con errores.')
            context = self.get_context_data()
            context['form'] = form
            return self.render_to_response(context)

class DashboardView(SidebarMenuMixin, PermissionMixin, LoginRequiredMixin, TemplateView):
    template_name = 'core/dashboard.html'
    permission_required = 'view_dashboard'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        request = self.request

        # Filtro de fecha (días)
        date_filter = request.GET.get('date_filter', '7')
        try:
            days = max(1, int(date_filter))
        except (TypeError, ValueError):
            days = 7
            date_filter = '7'

        now = timezone.now()
        start_date = now - timedelta(days=days)

        # Rol empresa
        try:
            is_empresa = request.user.is_authenticated and request.user.groups.filter(name__iexact='empresa').exists()
        except Exception:
            is_empresa = False

        fatigue_types = [AlertEvent.ALERT_MICROSLEEP, AlertEvent.ALERT_FATIGUE]

        # Cache de métricas por rango y usuario/rol (evitar f-strings anidados)
        if is_empresa:
            owner_key = 'empresa'
        else:
            owner_key = f"user:{request.user.id}" if request.user.is_authenticated else "user:anon"
        cache_key = f"dash:{owner_key}:{days}"
        metrics = cache.get(cache_key)

        if not metrics:
            sessions_qs = (
                MonitorSession.objects
                .filter(start_time__gte=start_date, start_time__lte=now)
                .select_related('user')
                .only('id', 'user', 'start_time', 'end_time', 'total_duration')
            )
            if not is_empresa and request.user.is_authenticated:
                sessions_qs = sessions_qs.filter(user=request.user)

            total_sessions = sessions_qs.count()
            active_users = sessions_qs.values('user').distinct().count()

            alerts_qs = AlertEvent.objects.filter(triggered_at__gte=start_date, triggered_at__lte=now)
            if not is_empresa and request.user.is_authenticated:
                alerts_qs = alerts_qs.filter(session__user=request.user)

            avg_fatigue = alerts_qs.filter(alert_type__in=fatigue_types).count()

            # Calcular cumplimiento de descansos (breaks tomados vs recomendados)
            # Contar alertas de break_reminder generadas en el período
            break_reminders_count = alerts_qs.filter(alert_type='break_reminder').count()
            
            # Contar solo las pausas que ocurrieron en sesiones con break_reminder
            # Esto excluye pausas manuales no relacionadas con los recordatorios
            sessions_with_breaks = sessions_qs.filter(
                alerts__alert_type='break_reminder',
                alerts__triggered_at__gte=start_date,
                alerts__triggered_at__lte=now
            ).distinct()
            
            breaks_taken_count = SessionPause.objects.filter(
                session__in=sessions_with_breaks,
                pause_time__gte=start_date,
                pause_time__lte=now,
            ).count()
            
            compliance_percent = 0.0
            if break_reminders_count > 0:
                compliance_percent = min(100.0, round((breaks_taken_count / break_reminders_count) * 100.0, 1))

            # Series por día
            date_list = [now - timedelta(days=i) for i in range(days - 1, -1, -1)]
            labels_by_day = [d.strftime('%d/%m') for d in date_list]
            sessions_by_day_map = (
                sessions_qs
                .annotate(day=TruncDate('start_time'))
                .values('day')
                .annotate(c=Count('id'))
            )
            count_map = {str(item['day']): item['c'] for item in sessions_by_day_map}
            sessions_by_day = [count_map.get((d.date()).isoformat(), 0) for d in date_list]

            alert_distribution = (
                alerts_qs
                .values('alert_type')
                .annotate(count=Count('id'))
                .order_by('-count')
            )
            alert_type_map = dict(AlertEvent.ALERT_TYPES)
            alert_labels = [alert_type_map.get(item['alert_type'], item['alert_type']).title() for item in alert_distribution]
            alert_data = [item['count'] for item in alert_distribution]

            # Top 10 usuarios (movido al caché)
            User = get_user_model()
            user_stats_raw = list(
                MonitorSession.objects
                .filter(start_time__gte=start_date, start_time__lte=now)
                .values('user__id', 'user__username', 'user__first_name', 'user__last_name', 'user__email')
                .annotate(
                    session_count=Count('id', distinct=True),
                    total_time_seconds=Sum('total_duration'),
                    fatigue_count=Count('alerts', filter=Q(alerts__alert_type__in=fatigue_types))
                )
                .order_by('-session_count')[:10]
            )
            
            # Enriquecer con ejercicios (solo para top 10)
            user_ids = [u['user__id'] for u in user_stats_raw]
            exercises_by_user = {}
            if user_ids:
                ex_counts = (
                    ExerciseSession.objects
                    .filter(user_id__in=user_ids, completed=True, completed_at__gte=start_date, completed_at__lte=now)
                    .values('user_id')
                    .annotate(count=Count('id'))
                )
                exercises_by_user = {item['user_id']: item['count'] for item in ex_counts}
            
            user_stats_data = []
            for u in user_stats_raw:
                user_stats_data.append({
                    'id': u['user__id'],
                    'username': u['user__username'],
                    'first_name': u['user__first_name'],
                    'last_name': u['user__last_name'],
                    'email': u['user__email'],
                    'session_count': u['session_count'],
                    'exercises_completed_count': exercises_by_user.get(u['user__id'], 0),
                    'fatigue_count': u['fatigue_count'],
                    'total_time_hours': round(u['total_time_seconds'] / 3600.0, 2) if u['total_time_seconds'] else 0.0,
                })

            metrics = {
                'total_sessions': total_sessions,
                'active_users': active_users,
                'avg_fatigue': avg_fatigue,
                'compliance_percent': compliance_percent,
                'labels_by_day': labels_by_day,
                'sessions_by_day': sessions_by_day,
                'alert_labels': alert_labels,
                'alert_data': alert_data,
                'user_stats': user_stats_data,
            }
            cache.set(cache_key, metrics, timeout=180)
        else:
            total_sessions = metrics['total_sessions']
            active_users = metrics['active_users']
            avg_fatigue = metrics['avg_fatigue']
            compliance_percent = metrics['compliance_percent']
            labels_by_day = metrics['labels_by_day']
            sessions_by_day = metrics['sessions_by_day']
            alert_labels = metrics['alert_labels']
            alert_data = metrics['alert_data']
            alert_distribution = []
            user_stats_data = metrics.get('user_stats', [])

        # Convertir user_stats_data a objetos con atributos para templates
        class UserStatProxy:
            def __init__(self, data):
                for k, v in data.items():
                    setattr(self, k, v)
        
        user_stats = [UserStatProxy(u) for u in user_stats_data]

        # Estado visual
        visual_score = 100
        visual_penalty = min(60, avg_fatigue * 3)
        visual_score = max(0, visual_score - visual_penalty)
        if compliance_percent >= 60:
            visual_score = min(100, visual_score + 5)

        if visual_score >= 75:
            estado_visual = 'Óptimo'; color_visual = 'green'; icon_visual = 'fa-eye'
        elif visual_score >= 45:
            estado_visual = 'Moderado'; color_visual = 'orange'; icon_visual = 'fa-eye'
        else:
            estado_visual = 'Bajo'; color_visual = 'red'; icon_visual = 'fa-tired'

        # Contexto
        context.update({
            'title': 'Dashboard',
            'title1': 'Panel principal',
            'date_filter': str(date_filter),
            'active_users': active_users,
            'total_sessions': total_sessions,
            'avg_fatigue': avg_fatigue,
            'compliance_percent': compliance_percent,
            'labels_by_day_json': json.dumps(labels_by_day),
            'sessions_by_day_json': json.dumps(sessions_by_day),
            'alert_distribution': list(alert_distribution) if alert_distribution else [],
            'has_sessions_data': total_sessions > 0,
            'has_alerts_data': len(alert_labels) > 0,
            'alert_labels_json': json.dumps(alert_labels),
            'alert_data_json': json.dumps(alert_data),
            'user_stats': user_stats,
            'estado_visual': estado_visual,
            'color_visual': color_visual,
            'icon': icon_visual,
        })

        return context
