"""
Comando para actualizar las estadísticas de salud visual de todos los usuarios.
Útil para recalcular estadísticas desde datos históricos.

Uso:
    python manage.py update_user_stats
    python manage.py update_user_stats --user-id=1
"""
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.db import transaction

User = get_user_model()


class Command(BaseCommand):
    help = 'Actualiza las estadísticas de salud visual de los usuarios'

    def add_arguments(self, parser):
        parser.add_argument(
            '--user-id',
            type=int,
            help='ID del usuario específico a actualizar (opcional)',
        )

    def handle(self, *args, **options):
        user_id = options.get('user_id')
        
        if user_id:
            try:
                user = User.objects.get(id=user_id)
                users = [user]
                self.stdout.write(f'Actualizando estadísticas para usuario: {user.username}')
            except User.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(f'Usuario con ID {user_id} no encontrado')
                )
                return
        else:
            users = User.objects.all()
            self.stdout.write(f'Actualizando estadísticas para {users.count()} usuarios')
        
        updated_count = 0
        
        with transaction.atomic():
            for user in users:
                try:
                    # Actualizar todas las estadísticas
                    user.update_monitoring_stats()
                    user.update_exercise_stats()
                    user.update_fatigue_stats()
                    user.update_streak()
                    
                    updated_count += 1
                    
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'✓ {user.username}: '
                            f'{user.total_sessions} sesiones, '
                            f'{user.total_monitoring_time} min, '
                            f'{user.exercises_completed} ejercicios, '
                            f'{user.current_streak} días racha'
                        )
                    )
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(f'✗ Error actualizando {user.username}: {str(e)}')
                    )
        
        self.stdout.write(
            self.style.SUCCESS(
                f'\n✅ Actualización completada: {updated_count} usuarios actualizados'
            )
        )
