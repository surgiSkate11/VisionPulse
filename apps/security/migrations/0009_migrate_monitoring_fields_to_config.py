# Generated manually for data migration
from django.db import migrations


def migrate_monitoring_fields(apps, schema_editor):
    """
    Migra los campos de configuración de monitoreo del modelo User 
    al modelo UserMonitoringConfig.
    """
    User = apps.get_model('security', 'User')
    UserMonitoringConfig = apps.get_model('monitoring', 'UserMonitoringConfig')
    
    for user in User.objects.all():
        # Obtener o crear la configuración de monitoreo
        config, created = UserMonitoringConfig.objects.get_or_create(user=user)
        
        # Migrar valores si existen en el modelo User
        if hasattr(user, 'ear_threshold') and user.ear_threshold:
            config.ear_threshold = user.ear_threshold
        
        if hasattr(user, 'low_blink_rate_threshold') and user.low_blink_rate_threshold:
            config.low_blink_rate_threshold = user.low_blink_rate_threshold
        
        if hasattr(user, 'high_blink_rate_threshold') and user.high_blink_rate_threshold:
            config.high_blink_rate_threshold = user.high_blink_rate_threshold
        
        if hasattr(user, 'yawn_mar_threshold') and user.yawn_mar_threshold:
            config.yawn_mar_threshold = user.yawn_mar_threshold
        
        if hasattr(user, 'low_light_threshold') and user.low_light_threshold:
            config.low_light_threshold = user.low_light_threshold
        
        config.save()


def reverse_migrate(apps, schema_editor):
    """
    Reversión de la migración (opcional, ya que los campos se eliminarán).
    """
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('security', '0008_alter_user_longest_streak'),
        ('monitoring', '0022_add_ear_yawn_thresholds'),
    ]

    operations = [
        migrations.RunPython(migrate_monitoring_fields, reverse_migrate),
    ]
