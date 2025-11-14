from django.core.management.base import BaseCommand
from django.db import transaction
from apps.monitoring.models import AlertTypeConfig, AlertEvent, UserMonitoringConfig
from django.db.models import Min

class Command(BaseCommand):
    help = 'Configura los comportamientos específicos de las alertas y sus métodos de resolución'

    def handle(self, *args, **options):
        # Obtener el intervalo de repetición más común configurado por los usuarios
        default_repeat_interval = UserMonitoringConfig.objects.aggregate(
            Min('alert_repeat_interval')
        )['alert_repeat_interval__min'] or 5  # 5 segundos por defecto

        # Configuraciones para cada tipo de alerta
        alert_configs = {
            # 1. Alertas con ejercicios (se repiten hasta completar el ejercicio)
            AlertEvent.ALERT_MICROSLEEP: {
                'description': 'Se detectaron ojos cerrados por tiempo prolongado. ¡Toma un descanso!',
                'repeat_max_per_hour': 3,     # Máximo de alertas DISTINTAS de microsueño por hora
                'resolution_type': 'exercise', # Se resuelve al completar el ejercicio
                'auto_pause': False,
            },
            AlertEvent.ALERT_FATIGUE: {
                'description': 'Signos de fatiga visual detectados. Realiza ejercicios de descanso.',
                'repeat_max_per_hour': 3,     # Máximo de alertas DISTINTAS de fatiga por hora
                'resolution_type': 'exercise', # Se resuelve al completar el ejercicio
                'auto_pause': False,
            },
            AlertEvent.ALERT_LOW_BLINK_RATE: {
                'description': 'Estás parpadeando muy poco. Recuerda parpadear conscientemente.',
                'repeat_max_per_hour': 3,
                'resolution_type': 'exercise',
                'auto_pause': False,
            },
            AlertEvent.ALERT_HIGH_BLINK_RATE: {
                'description': 'Exceso de parpadeo detectado. Indica posible fatiga.',
                'repeat_max_per_hour': 3,
                'resolution_type': 'exercise',
                'auto_pause': False,
            },
            AlertEvent.ALERT_FREQUENT_DISTRACT: {
                'description': 'Distracciones frecuentes detectadas. Intenta mantener el enfoque.',
                'repeat_max_per_hour': 3,
                'resolution_type': 'exercise',
                'auto_pause': False,
            },
            AlertEvent.ALERT_HEAD_TENSION: {
                'description': 'Posible tensión en el cuello detectada. Realiza estiramientos.',
                'repeat_max_per_hour': 3,
                'resolution_type': 'exercise',
                'auto_pause': False,
            },
            AlertEvent.ALERT_MICRO_RHYTHM: {
                'description': 'Patrones de somnolencia temprana detectados.',
                'repeat_max_per_hour': 3,
                'resolution_type': 'exercise',
                'auto_pause': False,
            },

            # 2. Alertas de postura y ambiente (se resuelven por histéresis)
            AlertEvent.ALERT_BAD_POSTURE: {
                'description': 'Tu postura no es la adecuada. Ajusta tu posición.',
                'repeat_max_per_hour': 3,
                'cooldown_seconds': 5,
                'resolution_type': 'hysteresis',  # Se resuelve al mantener postura correcta
                'hysteresis_timeout': 300,  # 5 minutos - tiempo mínimo para resolver
                'auto_pause': False,
            },
            AlertEvent.ALERT_BAD_DISTANCE: {
                'description': 'Estás demasiado cerca de la pantalla. Aléjate un poco.',
                'repeat_max_per_hour': 3,
                'cooldown_seconds': 5,
                'resolution_type': 'hysteresis',
                'hysteresis_timeout': 300,  # 5 minutos
                'auto_pause': False,
            },
            AlertEvent.ALERT_STRONG_GLARE: {
                'description': 'Se detecta reflejo excesivo. Ajusta la iluminación o tu posición.',
                'repeat_max_per_hour': 3,
                'cooldown_seconds': 5,
                'resolution_type': 'hysteresis',
                'hysteresis_timeout': 300,  # 5 minutos
                'auto_pause': False,
            },
            AlertEvent.ALERT_LOW_LIGHT: {
                'description': 'Iluminación insuficiente detectada. Mejora la iluminación.',
                'repeat_max_per_hour': 3,
                'cooldown_seconds': 5,
                'resolution_type': 'hysteresis',
                'hysteresis_timeout': 300,  # 5 minutos
                'auto_pause': False,
            },
            AlertEvent.ALERT_STRONG_LIGHT: {
                'description': 'Iluminación excesiva detectada. Reduce la luz ambiental.',
                'repeat_max_per_hour': 3,
                'cooldown_seconds': 5,
                'resolution_type': 'hysteresis',
                'hysteresis_timeout': 300,  # 5 minutos
                'auto_pause': False,
            },

            # 3. Alerta con histéresis (repite según intervalo hasta resolverse)
            AlertEvent.ALERT_CAMERA_OCCLUDED: {
                'description': 'La cámara está parcialmente obstruida. Verifica que no haya objetos bloqueando la vista.',
                'repeat_max_per_hour': 12,  # Mayor número para permitir repeticiones hasta resolverse
                'cooldown_seconds': 5,      # Respeta el intervalo de repetición
                'resolution_type': 'hysteresis', 
                'hysteresis_timeout': 30,   # 30 segundos para considerar resuelta
                'auto_pause': False,
            },

            # 3. Alertas que pausan el monitoreo (suenan una vez y pausan)
            AlertEvent.ALERT_DRIVER_ABSENT: {
                'description': 'No se detecta tu presencia. El monitoreo se pausará automáticamente.',
                'repeat_max_per_hour': 1,    # Solo suena una vez
                'cooldown_seconds': None,     # No necesita cooldown, pausa inmediatamente
                'resolution_type': 'auto_pause',
                'hysteresis_timeout': None,
                'auto_pause': True,
            },
            AlertEvent.ALERT_MULTIPLE_PEOPLE: {
                'description': 'Se detectan múltiples personas. Esta es una sesión individual.',
                'repeat_max_per_hour': 1,    # Solo suena una vez
                'cooldown_seconds': None,     # No necesita cooldown, pausa inmediatamente
                'resolution_type': 'auto_pause',
                'hysteresis_timeout': None,
                'auto_pause': True,
            },
        }

        with transaction.atomic():
            for alert_type, config in alert_configs.items():
                alert_config, created = AlertTypeConfig.objects.update_or_create(
                    alert_type=alert_type,
                    defaults={
                        'description': config['description'],
                        'repeat_max_per_hour': config['repeat_max_per_hour'],
                        'cooldown_seconds': config.get('cooldown_seconds', 5),  # valor por defecto = 5
                        'hysteresis_timeout': config.get('hysteresis_timeout'),
                        'resolution_type': config.get('resolution_type', 'exercise'),
                        'is_active': True,
                    }
                )
                
                # Guardar el comportamiento de auto-pausa en los metadatos
                metadata = alert_config.metadata or {}
                metadata['auto_pause'] = config.get('auto_pause', False)
                alert_config.metadata = metadata
                alert_config.save()

                status = 'Creada' if created else 'Actualizada'
                self.stdout.write(
                    self.style.SUCCESS(
                        f'{status} configuración para {alert_type}: '
                        f'max_repeticiones={config["repeat_max_per_hour"]}, '
                        f'intervalo={config.get("cooldown_seconds", 5)}s, '
                        f'auto_pausa={config.get("auto_pause", False)}'
                    )
                )

        self.stdout.write(self.style.SUCCESS('Configuración de comportamientos de alertas completada.'))