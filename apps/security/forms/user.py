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
            'username': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Elige tu nombre de usuario', 'autocomplete': 'username'}),
            'email': forms.EmailInput(attrs={'class': 'form-input', 'placeholder': 'tu@gmail.com', 'autocomplete': 'email'}),
            'first_name': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Tus nombres'}),
            'last_name': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Tus apellidos'}),
            'phone': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Teléfono'}),
            'image': forms.ClearableFileInput(),
        }

class CustomUserCreationForm(forms.ModelForm):
    password = forms.CharField(
        label='Contraseña',
        widget=forms.PasswordInput(attrs={'placeholder': 'Mínimo 8 caracteres', 'class': 'form-input', 'autocomplete': 'new-password'}),
        min_length=8,
        required=True
    )

    class Meta:
        model = User
        fields = [
            'email', 'username', 'first_name', 'last_name', 'password'
        ]
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Elige tu nombre de usuario', 'autocomplete': 'username'}),
            'email': forms.EmailInput(attrs={'class': 'form-input', 'placeholder': 'tu@gmail.com', 'autocomplete': 'email'}),
            'first_name': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Tus nombres'}),
            'last_name': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Tus apellidos'}),
        }

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password'])
        if commit:
            user.save()
        return user