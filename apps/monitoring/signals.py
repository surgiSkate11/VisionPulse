from __future__ import annotations

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model

from .models import AlertEvent, AlertTypeConfig

User = get_user_model()


@receiver(post_save, sender=AlertEvent)
def alertevent_post_save(sender, instance: AlertEvent, created: bool, **kwargs):
    # Solo al crear y si no hay clip asignado
    if not created:
        return
    if instance.voice_clip:
        return

    # Si hay un audio por defecto por tipo, úsalo
    try:
        cfg = AlertTypeConfig.objects.filter(alert_type=instance.alert_type, is_active=True).first()
    except Exception:
        cfg = None

    if cfg and cfg.default_voice_clip:
        instance.voice_clip = cfg.default_voice_clip
        try:
            instance.save(update_fields=['voice_clip'])
        except Exception:
            pass
        return
    return


# Eliminado: creación automática de EnhancedModelConfig por usuario (ya no existe)
