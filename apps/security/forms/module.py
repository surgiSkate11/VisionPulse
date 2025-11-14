import re
from django import forms
from django.forms import ModelForm
from apps.security.models import Module

class ModuleForm(ModelForm):
    class Meta:
        model = Module
        fields = [
            "name",
            "url",
            "menu",
            "description",
            "icon",
            "order",
            "is_active",
        ]
        # Mensajes de error personalizados para campos únicos
        error_messages = {
            "url": {
                "unique": "Ya existe un módulo con esta URL.",
            },
            "name": {
                "unique": "Ya existe un módulo con este nombre.",
            },
        }
        # Widgets personalizados para cada campo del formulario
        widgets = {
            "name": forms.TextInput(attrs={
                "placeholder": "Ingrese nombre del módulo",
                "id": "id_name",
                "class": "shadow-sm bg-gray-50 border border-gray-300 text-gray-900 rounded-lg focus:ring-blue-500 focus:border-blue-500 block w-full p-2.5 pr-12 dark:bg-principal dark:border-gray-600 dark:placeholder-gray-400 dark:text-gray-400 dark:focus:ring-blue-500 dark:focus:border-blue-500 dark:shadow-sm-light",
            }),
            "url": forms.TextInput(attrs={
                "placeholder": "Ingrese la URL del módulo",
                "id": "id_url",
                "class": "shadow-sm bg-gray-50 border border-gray-300 text-gray-900 rounded-lg focus:ring-blue-500 focus:border-blue-500 block w-full p-2.5 pr-12 dark:bg-principal dark:border-gray-600 dark:placeholder-gray-400 dark:text-gray-400 dark:focus:ring-blue-500 dark:focus:border-blue-500 dark:shadow-sm-light",
            }),
            "menu": forms.Select(attrs={
                "class": "shadow-sm bg-gray-50 border border-gray-300 text-gray-900 rounded-lg focus:ring-blue-500 focus:border-blue-500 block w-full p-2.5 dark:bg-principal dark:border-gray-600 dark:text-gray-400 dark:focus:ring-blue-500 dark:focus:border-blue-500",
            }),
            "description": forms.Textarea(attrs={
                "placeholder": "Descripción opcional del módulo",
                "class": "shadow-sm bg-gray-50 border border-gray-300 text-gray-900 rounded-lg focus:ring-blue-500 focus:border-blue-500 block w-full p-2.5 pr-12 dark:bg-principal dark:border-gray-600 dark:placeholder-gray-400 dark:text-gray-400 dark:focus:ring-blue-500 dark:focus:border-blue-500 dark:shadow-sm-light",
                "rows": 3,
            }),
            "icon": forms.TextInput(attrs={
                "placeholder": "Ingrese clase del ícono (ej. bi bi-house o fas fa-user)",
                "id": "id_icon",
                "class": "shadow-sm bg-gray-50 border border-gray-300 text-gray-900 rounded-lg focus:ring-blue-500 focus:border-blue-500 block w-full p-2.5 pr-12 dark:bg-principal dark:border-gray-600 dark:placeholder-gray-400 dark:text-gray-400 dark:focus:ring-blue-500 dark:focus:border-blue-500 dark:shadow-sm-light",
            }),
            "order": forms.NumberInput(attrs={
                "placeholder": "Ingrese el orden",
                "id": "id_order",
                "class": "shadow-sm bg-gray-50 border border-gray-300 text-gray-900 rounded-lg focus:ring-blue-500 focus:border-blue-500 block w-full p-2.5 pr-12 dark:bg-principal dark:border-gray-600 dark:placeholder-gray-400 dark:text-gray-400 dark:focus:ring-blue-500 dark:focus:border-blue-500 dark:shadow-sm-light",
            }),
            "is_active": forms.CheckboxInput(attrs={
                "class": "mt-1 block px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm",
            }),
            "permissions": forms.SelectMultiple(attrs={
                "class": "shadow-sm bg-gray-50 border border-gray-300 text-gray-900 rounded-lg focus:ring-blue-500 focus:border-blue-500 block w-full dark:bg-principal dark:border-gray-600 dark:text-gray-400 dark:focus:ring-blue-500 dark:focus:border-blue-500",
            }),
        }
        # Etiquetas personalizadas para los campos
        labels = {
            "name": "Nombre",
            "url": "Url",
            "menu": "Menú",
            "description": "Descripción",
            "icon": "Ícono",
            "order": "Orden",
            "is_active": "Activo",
            "permissions": "Permisos",
        }

    # Convierte el nombre a mayúsculas antes de guardar
    def clean_name(self):
        name = self.cleaned_data.get("name")
        return name.upper()

    # Valida el formato del campo icon para permitir FontAwesome y Bootstrap Icons
    def clean_icon(self):
        icon = self.cleaned_data['icon']
        if not icon:
            raise forms.ValidationError("El campo ícono es requerido.")

        # Patrones para FontAwesome v5, v6 y Bootstrap Icons (bi bi-...)
        patterns = [
            r'^(fas|far|fal|fad|fab|fa)\s+fa-[\w-]+$',      # fas fa-user (v5)
            r'^fa-(solid|regular|light|duotone|brands)\s+fa-[\w-]+$',  # fa-solid fa-user (v6)
            r'^fa-[\w-]+$',                                 # fa-user (formato simple)
            r'^bi bi-[\w-]+$',                              # Bootstrap Icons
        ]

        is_valid = any(re.match(pattern, icon) for pattern in patterns)

        if not is_valid:
            raise forms.ValidationError(
                "Formato de ícono inválido. Ejemplos válidos: "
                "'fas fa-user', 'fa-solid fa-person', 'fa-home', 'bi bi-person'"
            )

        return icon