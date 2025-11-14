from django.core.management.base import BaseCommand
from django.db import transaction

from apps.monitoring.models import AlertEvent, AlertExerciseMapping, AlertTypeConfig


EXERCISE_ALERTS = [
    # (alert_type, priority, default_description)
    (AlertEvent.ALERT_FATIGUE, 1, 'Signos de fatiga visual detectados. Realiza ejercicios de descanso.'),
    (AlertEvent.ALERT_LOW_BLINK_RATE, 2, 'Estás parpadeando muy poco. Recuerda parpadear conscientemente.'),
    (AlertEvent.ALERT_HIGH_BLINK_RATE, 2, 'Exceso de parpadeo detectado. Indica posible fatiga.'),
    (AlertEvent.ALERT_FREQUENT_DISTRACT, 3, 'Distracciones frecuentes detectadas. Intenta mantener el enfoque.'),
    (AlertEvent.ALERT_MICRO_RHYTHM, 3, 'Patrones de somnolencia temprana detectados.'),
    (AlertEvent.ALERT_HEAD_TENSION, 4, 'Posible tensión en el cuello detectada. Realiza estiramientos.'),
]


class Command(BaseCommand):
    help = (
        'Crea/actualiza mapeos AlertExerciseMapping y configuraciones AlertTypeConfig '
        'para las 6 alertas basadas en ejercicios (fatigue, low/high_blink_rate, '
        'frequent_distraction, micro_rhythm, head_tension). No modifica las 4 alertas ya funcionando.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true', default=False,
            help='Muestra lo que se haría sin escribir cambios.'
        )

    @transaction.atomic
    def handle(self, *args, **options):
        dry_run = options.get('dry_run', False)
        created_mappings = 0
        updated_mappings = 0
        created_configs = 0
        updated_configs = 0

        self.stdout.write(self.style.MIGRATE_HEADING('Seeding alert exercise mappings and type configs...'))

        for alert_type, priority, default_desc in EXERCISE_ALERTS:
            # Ensure AlertExerciseMapping exists (exercise can be set later in admin)
            mapping_defaults = {
                'exercise_id': None,  # left intentionally None; admin can bind concrete exercise later
                'is_active': True,
                'priority': priority,
            }
            try:
                mapping = AlertExerciseMapping.objects.filter(alert_type=alert_type).first()
                if mapping:
                    # Update priority/active but keep existing exercise binding
                    changes = []
                    if mapping.priority != priority:
                        mapping.priority = priority
                        changes.append('priority')
                    if not mapping.is_active:
                        mapping.is_active = True
                        changes.append('is_active')
                    if changes:
                        if not dry_run:
                            mapping.save(update_fields=changes + ['updated_at'])
                        updated_mappings += 1
                        self.stdout.write(self.style.WARNING(f'Updated mapping for {alert_type}: ' + ', '.join(changes)))
                    else:
                        self.stdout.write(self.style.NOTICE(f'Mapping OK for {alert_type}'))
                else:
                    if not dry_run:
                        AlertExerciseMapping.objects.create(alert_type=alert_type, **mapping_defaults)
                    created_mappings += 1
                    self.stdout.write(self.style.SUCCESS(f'Created mapping for {alert_type} (exercise=None, priority={priority})'))
            except Exception as e:
                self.stderr.write(self.style.ERROR(f'Error ensuring mapping for {alert_type}: {e}'))

            # Ensure AlertTypeConfig exists with a helpful description (voice clip optional)
            try:
                cfg, cfg_created = AlertTypeConfig.objects.get_or_create(
                    alert_type=alert_type,
                    defaults={
                        'description': default_desc,
                        'is_active': True,
                    }
                )
                if cfg_created:
                    created_configs += 1
                    self.stdout.write(self.style.SUCCESS(f'Created type config for {alert_type}'))
                else:
                    # Update description if empty and activate
                    changes = []
                    if not cfg.description:
                        cfg.description = default_desc
                        changes.append('description')
                    if not cfg.is_active:
                        cfg.is_active = True
                        changes.append('is_active')
                    if changes:
                        if not dry_run:
                            cfg.save(update_fields=changes + ['updated_at'])
                        updated_configs += 1
                        self.stdout.write(self.style.WARNING(f'Updated type config for {alert_type}: ' + ', '.join(changes)))
                    else:
                        self.stdout.write(self.style.NOTICE(f'Type config OK for {alert_type}'))
            except Exception as e:
                self.stderr.write(self.style.ERROR(f'Error ensuring type config for {alert_type}: {e}'))

        summary = (
            f'Mappings: +{created_mappings} created, ~{updated_mappings} updated | '
            f'TypeConfigs: +{created_configs} created, ~{updated_configs} updated'
        )
        if dry_run:
            summary = '[DRY RUN] ' + summary
        self.stdout.write(self.style.MIGRATE_LABEL(summary))

        if created_mappings or updated_mappings:
            self.stdout.write(
                self.style.HTTP_INFO(
                    '\nRecuerda vincular ejercicios concretos en Admin para que el botón "Ejercicio Recomendado" se muestre en el toast.'
                )
            )
