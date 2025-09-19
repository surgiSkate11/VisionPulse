from django.shortcuts import redirect, render
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django .contrib.auth.models import User
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from apps.security.forms.user import CustomUserCreationForm

# ----------------- Cerrar Sesion -----------------
@login_required
def signout(request):
    logout(request)
    return redirect("security:landing")

# # ----------------- Iniciar Sesion -----------------
def signin(request):
    # Si el usuario ya está autenticado, redirigir a home
    if request.user.is_authenticated:
        return redirect("security:home")
    
    data = {"title": "Login", "title1": "Inicio de Sesión"}
    if request.method == "GET":
        success_messages = messages.get_messages(request)
        return render(request, "security/auth/signin.html", {
            "form": AuthenticationForm(),
            "success_messages": success_messages,
            **data
        })
    else:
        # Permitir login con email (gmail) o username
        post_data = request.POST.copy()
        login_input = post_data.get('login', '').strip()
        post_data['username'] = login_input
        form = AuthenticationForm(data=post_data)
        if form.is_valid():
            password = form.cleaned_data.get('password')
            user = None
            # Si el input parece un email, buscar el username asociado
            if '@' in login_input:
                from apps.security.models import User
                try:
                    user_obj = User.objects.get(email__iexact=login_input)
                    user = authenticate(request, username=user_obj.email, password=password)
                except User.DoesNotExist:
                    user = None
            else:
                user = authenticate(request, username=login_input, password=password)
            if user is not None:
                login(request, user)
                return redirect("security:home")
            else:
                form.add_error(None, "El usuario o la contraseña son incorrectos")
        return render(request, "security/auth/signin.html", {
            "form": form,
            **data
        })

# # ----------------- Registrar Nuevo Usuario -----------------
def signup(request):
    # Si el usuario ya está autenticado, redirigir a home
    if request.user.is_authenticated:
        return redirect("core:home")
    
    data = {"title1": "Registro", "title2": "Crea tu cuenta"}
    if request.method == "POST":
        form = CustomUserCreationForm(request.POST, request.FILES)
        if form.is_valid():
            user = form.save()
            # Autenticar explícitamente para obtener backend
            user_auth = authenticate(request, email=form.cleaned_data['email'], password=form.cleaned_data['password'])
            if user_auth is not None:
                login(request, user_auth)
            # Mostrar fragmento de éxito y redirigir a signin
            return render(request, "security/auth/signup.html", {"form": CustomUserCreationForm(), "cuenta_creada": True, **data})
        else:
            return render(request, "security/auth/signup.html", {"form": form, **data})
    else:
        form = CustomUserCreationForm()
        return render(request, "security/auth/signup.html", {"form": form, **data})