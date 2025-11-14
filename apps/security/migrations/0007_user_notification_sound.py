# Generated migration

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('security', '0006_delete_usermonitoringconfig'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='notification_sound',
            field=models.CharField(
                choices=[
                    ('sound1', 'Campana Suave'),
                    ('sound2', 'Notificación Moderna'),
                    ('sound3', 'Tono Sutil'),
                    ('sound4', 'Alerta Digital'),
                    ('sound5', 'Campana Cristalina'),
                    ('sound6', 'Ping Elegante')
                ],
                default='sound1',
                help_text='Sonido que se reproducirá cuando lleguen notificaciones',
                max_length=20,
                verbose_name='Sonido de Notificación'
            ),
        ),
        migrations.AddField(
            model_name='user',
            name='notification_sound_enabled',
            field=models.BooleanField(
                default=True,
                help_text='Activar/desactivar sonidos de notificación',
                verbose_name='Sonido Habilitado'
            ),
        ),
        migrations.AddField(
            model_name='user',
            name='total_monitoring_time',
            field=models.PositiveIntegerField(
                default=0,
                help_text='Tiempo total de monitoreo en minutos'
            ),
        ),
        migrations.AddField(
            model_name='user',
            name='total_sessions',
            field=models.PositiveIntegerField(
                default=0,
                help_text='Total de sesiones completadas'
            ),
        ),
        migrations.AddField(
            model_name='user',
            name='current_streak',
            field=models.PositiveIntegerField(
                default=0,
                help_text='Racha actual de días consecutivos'
            ),
        ),
    ]
