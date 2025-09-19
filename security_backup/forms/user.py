from django import forms
from django.contrib.auth.forms import UserCreationForm
from apps.security.models import User

class UserForm(forms.ModelForm):
    class Meta:
        model = User
        fields = [
            'username', 'email', 'first_name', 'last_name',
            'phone', 'image',
            'is_active', 'is_staff', 'is_superuser'
        ]
        widgets = {
            'icon': forms.TextInput(attrs={'placeholder': 'fa-solid fa-user'}),
            'order': forms.NumberInput(attrs={'min': 0}),
            'phone': forms.TextInput(attrs={'placeholder': 'Teléfono'}),
            'image': forms.ClearableFileInput(),
        }

class CustomUserCreationForm(forms.ModelForm):
    password = forms.CharField(
        label='Contraseña',
        widget=forms.PasswordInput(attrs={'placeholder': 'Mínimo 8 caracteres'}),
        min_length=8,
        required=True
    )

    country = forms.CharField(
        label='País',
        max_length=100,
        required=True,
        widget=forms.TextInput(attrs={'placeholder': 'Selecciona tu país', 'readonly': 'readonly'})
    )

    class Meta:
        model = User
        fields = [
            'username', 'email', 'first_name', 'last_name',
            'phone', 'image', 'country', 'password'
        ]
        widgets = {
            'phone': forms.TextInput(attrs={'placeholder': 'Teléfono'}),
            'image': forms.ClearableFileInput(),
        }

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password'])
        user.country = self.cleaned_data['country']
        if commit:
            user.save()
        return user