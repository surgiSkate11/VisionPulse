from django.http import JsonResponse
from django.contrib.auth.decorators import login_required

@login_required
def get_user_config(request):
    """
    Endpoint para obtener la configuración del usuario.
    """
    user = request.user
    user_cfg = getattr(user, 'monitoring_config', None)
    # Exponer valores desde monitoring_config con defaults sensatos
    config = {
        'alert_volume': getattr(user_cfg, 'alert_volume', 0.7) if user_cfg else 0.7,
        'alert_repeat_interval': getattr(user_cfg, 'alert_repeat_interval', 10) if user_cfg else 10,
        'notify_inactive_tab': getattr(user_cfg, 'notify_inactive_tab', True) if user_cfg else True,
        'repeat_max_per_hour': getattr(user_cfg, 'repeat_max_per_hour', 3) if user_cfg else 3,
        'ear_threshold': getattr(user_cfg, 'ear_threshold', 0.20) if user_cfg else 0.20,
        'microsleep_duration_seconds': getattr(user_cfg, 'microsleep_duration_seconds', 5.0) if user_cfg else 5.0,
        'low_blink_rate_threshold': getattr(user_cfg, 'low_blink_rate_threshold', 10) if user_cfg else 10,
        'high_blink_rate_threshold': getattr(user_cfg, 'high_blink_rate_threshold', 35) if user_cfg else 35,
        'break_reminder_interval': getattr(user_cfg, 'break_reminder_interval', 20) if user_cfg else 20,
        'data_collection_consent': getattr(user_cfg, 'data_collection_consent', True) if user_cfg else True,
        'alert_cooldown_seconds': getattr(user_cfg, 'alert_cooldown_seconds', 60) if user_cfg else 60,
        'detection_delay_seconds': getattr(user_cfg, 'detection_delay_seconds', 5) if user_cfg else 5,
        'hysteresis_timeout_seconds': getattr(user_cfg, 'hysteresis_timeout_seconds', 30) if user_cfg else 30,
    }
    return JsonResponse(config)