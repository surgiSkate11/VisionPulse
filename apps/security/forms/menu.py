import re
from django import forms
from django.forms import ModelForm
from django.core.exceptions import ValidationError

from apps.security.models import Menu, Module

class MenuForm(ModelForm):
    class Meta:
        model = Menu
        fields = [
            "name",
            "icon",
            "order",
        ]
        error_messages = {
            "name": {
                "unique": "Ya existe un menu con este nombre.",
            },
        }
        widgets = {
            # Input para el nombre del menú
            "name": forms.TextInput(attrs={
                "placeholder": "Ingrese nombre del menu",
                "id": "id_name",
                "class": "shadow-sm bg-gray-50 border border-gray-300 text-gray-900 rounded-lg focus:ring-blue-500 focus:border-blue-500 block w-full p-2.5 pr-12 dark:bg-principal dark:border-gray-600 dark:placeholder-gray-400 dark:text-gray-400 dark:focus:ring-blue-500 dark:focus:border-blue-500 dark:shadow-sm-light",
            }),
            # Input para el ícono del menú
            "icon": forms.TextInput(attrs={
                "placeholder": "Ingrese clase del ícono (ej. bi bi-house)",
                "id": "id_icon",
                "class": "shadow-sm bg-gray-50 border border-gray-300 text-gray-900 rounded-lg focus:ring-blue-500 focus:border-blue-500 block w-full p-2.5 pr-12 dark:bg-principal dark:border-gray-600 dark:placeholder-gray-400 dark:text-gray-400 dark:focus:ring-blue-500 dark:focus:border-blue-500 dark:shadow-sm-light",
            }),
            # Input para el orden del menú
            "order": forms.NumberInput(attrs={
                "placeholder": "Ingrese el orden",
                "id": "id_order",
                "class": "shadow-sm bg-gray-50 border border-gray-300 text-gray-900 rounded-lg focus:ring-blue-500 focus:border-blue-500 block w-full p-2.5 pr-12 dark:bg-principal dark:border-gray-600 dark:placeholder-gray-400 dark:text-gray-400 dark:focus:ring-blue-500 dark:focus:border-blue-500 dark:shadow-sm-light",
            }),
        }
        labels = {
            "name": "Nombre Menu",
            "icon": "Ícono",
            "order": "Orden",
        }

    def clean_name(self):
        # Convierte el nombre a mayúsculas para mantener consistencia
        name = self.cleaned_data.get("name")
        return name.upper()
    
    def clean_icon(self):
        icon = self.cleaned_data['icon']
        if not icon:
            raise forms.ValidationError("El campo ícono es requerido.")
        
        # Patrones para FontAwesome v5/v6 y Bootstrap Icons (bi bi-*)
        patterns = [
            r'^(fas|far|fal|fad|fab|fa)\s+fa-\w+',      # fas fa-user (FontAwesome v5)
            r'^fa-(solid|regular|light|duotone|brands)\s+fa-\w+',  # fa-solid fa-user (FontAwesome v6)
            r'^fa-\w+$',                                 # fa-user (formato simple FontAwesome)
            r'^bi\s+bi-\w+',                             # bi bi-house (Bootstrap Icons)
        ]
        
        # Valida si el ícono coincide con alguno de los patrones permitidos
        is_valid = any(re.match(pattern, icon) for pattern in patterns)
        
        if not is_valid:
            raise forms.ValidationError(
                "Formato de ícono inválido. Ejemplos válidos: "
                "'fas fa-user', 'fa-solid fa-person', 'fa-home', 'bi bi-house'"
            )
        
        return icon