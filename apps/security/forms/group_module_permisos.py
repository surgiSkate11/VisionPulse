from django import forms
from django.forms import ModelForm
from apps.security.models import GroupModulePermission

class GroupModulePermissionForm(ModelForm):
    class Meta:
        model = GroupModulePermission
        fields = [
            "group",
            "module"
        ]
        error_messages = {
            "group": {
                "unique": "Ya existe un grupo con este nombre.",
            },
            "module": {
                "unique": "Ya existe un módulo con este nombre.",
            },
        }
        widgets = {
            "group": forms.Select(attrs={
                "class": "shadow-sm bg-gray-50 border border-gray-300 text-gray-900 rounded-lg focus:ring-blue-500 focus:border-blue-500 block w-full p-2.5 dark:bg-principal dark:border-gray-600 dark:text-gray-400 dark:focus:ring-blue-500 dark:focus:border-blue-500",
            }),
            "module": forms.Select(attrs={
                "class": "shadow-sm bg-gray-50 border border-gray-300 text-gray-900 rounded-lg focus:ring-blue-500 focus:border-blue-500 block w-full p-2.5 dark:bg-principal dark:border-gray-600 dark:text-gray-400 dark:focus:ring-blue-500 dark:focus:border-blue-500",
            }),
        }
        labels = {
            "group": "Grupo",
            "module": "Módulo"
        }

    # def clean(self):
    #     cleaned_data = super().clean()
    #     module = cleaned_data.get('module')
    #     permissions = cleaned_data.get('permissions')
    #     if module and permissions:
    #         valid_permissions = module.permissions.all()
    #         for perm in permissions:
    #             if perm not in valid_permissions:
    #                 raise forms.ValidationError(
    #                     f"El permiso '{perm}' no pertenece al módulo '{module}'."
    #                 )
    #     return cleaned_data
    