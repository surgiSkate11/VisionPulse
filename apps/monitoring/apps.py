from django.apps import AppConfig


class MonitoringConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.monitoring'

    def ready(self):
        # Importa señales para generación de audio de alertas
        from . import signals  # noqa: F401
