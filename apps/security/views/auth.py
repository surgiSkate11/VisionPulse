from django.shortcuts import redirect, render
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django .contrib.auth.models import User, Group
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from apps.security.forms.user import CustomUserCreationForm
from django.views.decorators.http import require_http_methods

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
@require_http_methods(["GET", "POST"])
def signup(request):
    """
    Vista para manejar el registro de usuarios usando CustomUserCreationForm.
    - usa request.POST y request.FILES
    - al guardar muestra el modal 'cuenta_creada' en la plantilla
    """
    cuenta_creada = False
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST, request.FILES)
        if form.is_valid():
            # form.save() ya asigna password y otros campos según implementación del form
            user = form.save(commit=False)
            # normalizar email por seguridad
            if getattr(user, 'email', None):
                user.email = user.email.lower()
            user.save()
            
            # Asignar automáticamente al grupo "General"
            try:
                general_group, created = Group.objects.get_or_create(name='General')
                user.groups.add(general_group)
            except Exception as e:
                messages.warning(request, f"Usuario creado, pero no se pudo asignar al grupo General: {e}")
            
            messages.success(request, "Cuenta creada correctamente.")
            cuenta_creada = True
            # resetear formulario vacío para evitar mostrar datos antiguos
            form = CustomUserCreationForm()
    else:
        form = CustomUserCreationForm()

    return render(request, 'security/auth/signup.html', {
        'form': form,
        'cuenta_creada': cuenta_creada
    })