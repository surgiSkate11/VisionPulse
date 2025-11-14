from django.urls import path
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.http import require_POST
import json

from apps.security.views.auth import signin, signout, signup
from apps.security.views.menu import MenuCreateView, MenuDeleteView, MenuListView, MenuUpdateView
from apps.security.views.module import ModuleCreateView, ModuleDeleteView, ModuleListView, ModuleUpdateView
from apps.security.views.usuarios import UserCreateView, UserDeleteView, UserListView, UserUpdateView
from apps.security.views.grupo import GroupListView, GroupUpdateView, GroupCreateView, GroupDeleteView
from apps.security.views.grupo_modulo_permisos import GroupModulePermissionListView, GroupModulePermissionCreateView, GroupModulePermissionUpdateView, GroupModulePermissionDeleteView, GroupModulePermissionAjaxView
from apps.security.views.seguridad import SeguridadView
from apps.security.views.home import HomeView
from apps.security.views.seguridad import landing_view, terms, privacy
from apps.security.views.settings import settings_view
from apps.security.views.set_group_session import SetGroupSessionView

@require_POST
def save_notification_settings(request):
    try:
        data = json.loads(request.body)
        user = request.user
        user.notification_sound = data.get('notification_sound', 'sound1')
        user.notification_sound_enabled = data.get('notification_sound_enabled', True)
        user.save()
        return JsonResponse({'status': 'success', 'message': 'Configuración guardada correctamente'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

def clear_login_notification(request):
    """Limpia la notificación de login de la sesión"""
    if 'show_login_notification' in request.session:
        del request.session['show_login_notification']
    return JsonResponse({'status': 'success'})

def get_user_audio_config(request):
    """Obtiene la configuración de audio del usuario"""
    if not request.user.is_authenticated:
        return JsonResponse({'status': 'error', 'message': 'No autenticado'}, status=401)
    
    user = request.user
    return JsonResponse({
        'status': 'success',
        'config': {
            'notification_sound': user.notification_sound,
            'notification_sound_enabled': user.notification_sound_enabled,
            'alert_volume': float(user.alert_volume) if hasattr(user, 'alert_volume') else 0.7
        }
    })


app_name='security' # define un espacio de nombre para la aplicacion
urlpatterns = [

    # Rutas principales de security
    path('', HomeView.as_view(), name='home'),
    path('landing/', landing_view, name='landing'),
    path('security/', SeguridadView.as_view(), name='controller'),
    # path('profile/', profile_view, name='profile'),
    # path('configuraciones/', configuration_view, name='configuraciones'),
    path('terminos/', terms, name='terms'),
    path('privacy/', privacy, name='privacy'),
    # rutas de modulos
    path('module_list/',ModuleListView.as_view() ,name="module_list"),
    path('module_create/', ModuleCreateView.as_view(),name="module_create"),
    path('module_update/<int:pk>/', ModuleUpdateView.as_view(),name='module_update'),
    path('module_delete/<int:pk>/', ModuleDeleteView.as_view(),name='module_delete'),

# rutas de menus
  path('menu_list/',MenuListView.as_view() ,name="menu_list"),
  path('menu_create/', MenuCreateView.as_view(),name="menu_create"),
  path('menu_update/<int:pk>/', MenuUpdateView.as_view(),name='menu_update'),
  path('menu_delete/<int:pk>/', MenuDeleteView.as_view(),name='menu_delete'),

  # rutas de autenticacion
  path('signin/', signin, name='signin'),
  path('login/', signin, name='login'),
  path('signup/', signup, name='signup'),
  path('logout/', signout, name='signout'),


# rutas de usuarios
path('user_list/', UserListView.as_view(), name="user_list"),
path('user_create/', UserCreateView.as_view(), name="user_create"),
path('user_update/<int:pk>/', UserUpdateView.as_view(), name='user_update'),
path('user_delete/<int:pk>/', UserDeleteView.as_view(), name='user_delete'),

# rutas de grupos
path('group_list/', GroupListView.as_view(), name="group_list"),
path('group_create/', GroupCreateView.as_view(), name="group_create"),
path('group_update/<int:pk>/', GroupUpdateView.as_view(), name='group_update'),
path('group_delete/<int:pk>/', GroupDeleteView.as_view(), name='group_delete'),



# rutas de grupos_modulos_permisos
path('group_module_permission_list/', GroupModulePermissionListView.as_view(), name="group_module_permission_list"),
path('group_module_permission_create/', GroupModulePermissionCreateView.as_view(), name="group_module_permission_create"),
path('group_module_permission_update/<int:pk>/', GroupModulePermissionUpdateView.as_view(), name='group_module_permission_update'),
path('group_module_permission_delete/<int:pk>/', GroupModulePermissionDeleteView.as_view(), name='group_module_permission_delete'),
path('group_module_permission_ajax/', GroupModulePermissionAjaxView.as_view(), name='group_module_permission_ajax'),
path('group_module_permission_ajax/<int:pk>/', GroupModulePermissionAjaxView.as_view(), name='group_module_permission_ajax_delete'),

# ruta de configuracion
path('settings/', settings_view, name='settings'),
path('notification-settings/', lambda request: render(request, 'security/notification_settings.html'), name='notification_settings'),
path('api/save-notification-settings/', lambda request: save_notification_settings(request), name='save_notification_settings'),
path('api/clear-login-notification/', lambda request: clear_login_notification(request), name='clear_login_notification'),
path('api/get-user-audio-config/', lambda request: get_user_audio_config(request), name='get_user_audio_config'),
path('set_group_session/', SetGroupSessionView.as_view(), name='set_group_session'),

# Rutas del menú de usuario (core)
path('profile/', lambda request: __import__('apps.core.views', fromlist=['ProfileView']).ProfileView.as_view()(request), name='profile'),
path('user-settings/', lambda request: __import__('apps.core.views', fromlist=['UserSettingsView']).UserSettingsView.as_view()(request), name='user_settings'),
path('dashboard/', lambda request: __import__('apps.core.views', fromlist=['DashboardView']).DashboardView.as_view()(request), name='dashboard'),
]