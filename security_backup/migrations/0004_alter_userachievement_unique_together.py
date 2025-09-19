# Dividir la migración problemática en dos pasos para evitar el error de dependencia de campos.
from django.db import migrations

class Migration(migrations.Migration):
    dependencies = [
        ('security', '0003_achievement_user_bio_user_birth_date_and_more'),
    ]
    operations = [
        migrations.AlterUniqueTogether(
            name='userachievement',
            unique_together=None,
        ),
    ]
