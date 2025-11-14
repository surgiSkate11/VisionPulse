# Generated migration

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('monitoring', '0020_alertevent_last_repeated_at_alertevent_repeat_count_and_more'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='usermonitoringconfig',
            name='notification_mode',
        ),
    ]
