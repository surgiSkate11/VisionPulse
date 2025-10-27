"""
Signals para actualizar automáticamente las estadísticas de salud visual del usuario.
"""
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone
from datetime import date
from apps.monitoring.models import MonitorSession, AlertEvent
from apps.exercises.models import ExerciseSession


@receiver(post_save, sender=MonitorSession)
def update_user_session_stats(sender, instance, created, **kwargs):
    """
    Actualiza las estadísticas del usuario cuando se guarda una sesión de monitoreo.
    """
    if instance.status == 'completed' and instance.end_time:
        user = instance.user
        
        # Actualizar total de sesiones
        user.total_sessions = MonitorSession.objects.filter(
            user=user,
            status='completed'
        ).count()
        
        # Actualizar tiempo total de monitoreo (en minutos)
        total_duration = MonitorSession.objects.filter(
            user=user,
            status='completed'
        ).aggregate(
            total=models.Sum('total_duration')
        )['total'] or 0
        
        # Si no hay total_duration, usar duration_seconds
        if total_duration == 0:
            total_duration = MonitorSession.objects.filter(
                user=user,
                status='completed'
            ).aggregate(
                total=models.Sum('duration_seconds')
            )['total'] or 0
        
        user.total_monitoring_time = int(total_duration / 60) if total_duration else 0
        
        # Actualizar racha (streak)
        update_user_streak(user)
        
        user.save(update_fields=['total_sessions', 'total_monitoring_time', 'current_streak', 'longest_streak', 'last_streak_update'])


@receiver(post_save, sender=AlertEvent)
def update_user_alert_stats(sender, instance, created, **kwargs):
    """
    Actualiza las estadísticas de alertas del usuario.
    """
    if created and instance.alert_type == 'fatigue':
        user = instance.session.user
        
        # Contar episodios de fatiga
        user.fatigue_episodes = AlertEvent.objects.filter(
            session__user=user,
            alert_type='fatigue'
        ).count()
        
        user.save(update_fields=['fatigue_episodes'])


@receiver(post_save, sender=ExerciseSession)
def update_user_exercise_stats(sender, instance, created, **kwargs):
    """
    Actualiza las estadísticas de ejercicios del usuario.
    """
    user = instance.user
    
    # Actualizar ejercicios completados
    user.exercises_completed = ExerciseSession.objects.filter(
        user=user,
        completed=True
    ).count()
    
    user.save(update_fields=['exercises_completed'])


def update_user_streak(user):
    """
    Actualiza la racha de días consecutivos del usuario.
    """
    from django.db import models
    
    today = date.today()
    
    # Si es el primer update o es un nuevo día
    if not user.last_streak_update or user.last_streak_update < today:
        # Obtener sesiones de los últimos días
        sessions_by_date = MonitorSession.objects.filter(
            user=user,
            status='completed'
        ).values('start_time__date').annotate(
            count=models.Count('id')
        ).order_by('-start_time__date')
        
        if sessions_by_date.exists():
            dates_with_sessions = [item['start_time__date'] for item in sessions_by_date]
            
            # Calcular racha actual
            current_streak = 0
            check_date = today
            
            for session_date in dates_with_sessions:
                if session_date == check_date or session_date == check_date - timezone.timedelta(days=1):
                    current_streak += 1
                    check_date = session_date - timezone.timedelta(days=1)
                else:
                    break
            
            user.current_streak = current_streak
            
            # Actualizar racha más larga
            if current_streak > user.longest_streak:
                user.longest_streak = current_streak
            
            user.last_streak_update = today


# Importar models aquí para evitar importación circular
from django.db import models
