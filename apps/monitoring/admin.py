from django.contrib import admin

# Register your models here.
from .models import *

from django.contrib import admin
from django.apps import apps

# Cambia 'monitoring' por el nombre de tu app
app = apps.get_app_config('monitoring')

for model_name, model in app.models.items():
    try:
        admin.site.register(model)
    except admin.sites.AlreadyRegistered:
        pass
