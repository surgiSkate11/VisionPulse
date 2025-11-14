
from django.views.decorators.csrf import requires_csrf_token
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from apps.security.components.sidebar_menu_mixin import SidebarMenuMixin
from django.contrib import messages
from django.views.decorators.http import require_http_methods
from rest_framework import generics, status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.authtoken.models import Token
from django.conf import settings
from django.utils import timezone
from django.http import JsonResponse
import json

from ..models import User
from ..serializers import (
    UserSerializer, UserRegistrationSerializer, 
    UserProfileSerializer,
    # AchievementSerializer, UserAchievementSerializer
)

# === FUNCIONES AUXILIARES EXISTENTES ===

def ajax_login_required(view_func):
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'message': 'Sesión expirada. Inicia sesión de nuevo.'}, status=401)
            from django.contrib.auth.views import redirect_to_login
            return redirect_to_login(request.get_full_path())
        return view_func(request, *args, **kwargs)
    return wrapper

@requires_csrf_token
def custom_csrf_failure(request, reason=""):
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'success': False, 'message': 'CSRF inválido o sesión expirada.'}, status=403)
    from django.views.csrf import csrf_failure
    return csrf_failure(request, reason=reason)

# === VISTAS DE API PARA STUDER ===

class UserRegistrationView(generics.CreateAPIView):
    """API endpoint para registro de nuevos usuarios"""
    queryset = User.objects.all()
    serializer_class = UserRegistrationSerializer
    permission_classes = [permissions.AllowAny]
    
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Crear usuario
        user = serializer.save()
        
        # Crear token de autenticación
        token, created = Token.objects.get_or_create(user=user)
        
        
        # Añadir XP inicial de bienvenida
        user.add_xp(settings.STUDER_SETTINGS['GAMIFICATION']['XP_PER_TASK_COMPLETION'])
        
        return Response({
            'user': UserSerializer(user).data,
            'token': token.key,
            'message': '¡Bienvenido a Studer! Tu cuenta ha sido creada exitosamente.'
        }, status=status.HTTP_201_CREATED)


class UserLoginView(generics.GenericAPIView):
    """API endpoint para autenticación de usuarios"""
    permission_classes = [permissions.AllowAny]
    
    def post(self, request):
        username = request.data.get('username')
        password = request.data.get('password')
        
        if not username or not password:
            return Response({
                'error': 'Username y password son requeridos'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        user = authenticate(username=username, password=password)
        
        if user:
            if user.is_active:
                token, created = Token.objects.get_or_create(user=user)
                
                # Actualizar última actividad
                user.last_activity = timezone.now()
                user.save()
                
                return Response({
                    'user': UserSerializer(user).data,
                    'token': token.key,
                    'message': f'¡Bienvenido de vuelta, {user.get_full_name}!'
                }, status=status.HTTP_200_OK)
            else:
                return Response({
                    'error': 'Tu cuenta está desactivada. Contacta al soporte.'
                }, status=status.HTTP_403_FORBIDDEN)
        else:
            return Response({
                'error': 'Credenciales inválidas'
            }, status=status.HTTP_401_UNAUTHORIZED)


class UserProfileView(generics.RetrieveUpdateAPIView):
    """API endpoint para ver y actualizar el perfil del usuario"""
    serializer_class = UserProfileSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_object(self):
        return self.request.user


class UserStatsView(generics.GenericAPIView):
    """API endpoint para obtener estadísticas del usuario"""
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        user = request.user
        
        # Calcular estadísticas adicionales
        achievements_count = user.achievements.count()
        level_progress = user.get_level_progress()
        
        stats = {
            'user_info': {
                'username': user.username,
                'full_name': user.get_full_name,
                'level': user.current_level,
                'total_xp': user.total_xp,
                'level_progress': level_progress,
                'current_streak': user.current_streak,
                'longest_streak': user.longest_streak,
            },
            'study_stats': {
                'total_study_time_hours': round(user.total_study_time / 60, 2),
                'tasks_completed': user.tasks_completed,
                'notes_created': user.notes_created,
                'achievements_earned': achievements_count,
            },
            'account_info': {
                'is_premium': user.is_premium_active(),
                'member_since': user.date_joined.strftime('%Y-%m-%d'),
                'last_activity': user.last_activity.strftime('%Y-%m-%d %H:%M'),
            }
        }
        
        return Response(stats, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def add_xp(request):
    """Agregar XP al usuario autenticado"""
    try:
        amount = int(request.data.get('amount', 0))
        reason = request.data.get('reason', 'Actividad completada')
        
        if amount <= 0:
            return Response({'error': 'Amount must be positive'}, status=status.HTTP_400_BAD_REQUEST)
        
        user = request.user
        user.add_xp(amount, reason)
        
        return Response({
            'success': True,
            'new_xp': user.experience_points,
            'new_level': user.level,
            'level_progress': user.get_level_progress()
        })
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def update_streak(request):
    """Actualizar racha de estudio del usuario"""
    try:
        user = request.user
        user.update_study_streak()
        
        return Response({
            'success': True,
            'current_streak': user.current_streak,
            'best_streak': user.best_streak
        })
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


# === VISTAS DE LOGROS ===
# Comentadas temporalmente hasta implementar el módulo de logros

# class AchievementListView(generics.ListAPIView):
#     """Lista todos los logros disponibles"""
#     queryset = Achievement.objects.filter(is_active=True)
#     serializer_class = AchievementSerializer
#     permission_classes = [permissions.IsAuthenticated]


# class UserAchievementListView(generics.ListAPIView):
#     """Lista los logros obtenidos por el usuario autenticado"""
#     serializer_class = UserAchievementSerializer
#     permission_classes = [permissions.IsAuthenticated]
#     
#     def get_queryset(self):
#         return UserAchievement.objects.filter(
#             user=self.request.user
#         ).order_by('-earned_at')


# Vista tradicional para el dashboard
@login_required
def dashboard_view(request):
    """Vista del dashboard principal"""
    user = request.user
    student = getattr(user, 'student_profile', None)
    recent_achievements = []
    if student:
        recent_achievements = student.achievements.order_by('-achieved_at')[:5]
    context = {
        'user': user,
        'level_progress': user.get_level_progress(),
        'recent_achievements': recent_achievements,
        'is_premium': user.is_premium_active(),
    }
    # Usar SidebarMenuMixin para poblar sidebar_menu y herramientas_menu
    context = SidebarMenuMixin().get_context_data(context=context, request=request)
    context['request'] = request
    return render(request, 'home.html', context)


# === VISTA ONBOARDING MULTIPASO ===
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

@login_required
def onboarding(request):
    steps = [
        'Datos básicos',
        'Preferencias',
        'Estilo de aprendizaje',
        'Personalización',
        'Resumen'
    ]
    step = int(request.POST.get('step', 1))
    error = None

    if request.method == 'POST' and step < 5:
        # Aquí podrías guardar los datos del paso actual si lo deseas
        # Validaciones mínimas para el paso 1
        if step == 1:
            if not request.POST.get('first_name') or not request.POST.get('last_name') or not request.POST.get('email'):
                error = 'Por favor completa los campos obligatorios.'
            else:
                step += 1
        else:
            step += 1
    elif request.method == 'POST' and step == 5:
        # Finalizar onboarding
        return redirect('core:home')

    context = {
        'step': step,
        'steps': steps,
        'error': error,
        'user': request.user,
    }
    return render(request, 'onboarding/onboarding.html', context)
