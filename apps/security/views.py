from django.http import JsonResponse
from django.views.decorators.csrf import requires_csrf_token
# from django.shortcuts import render

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

# def home(request): 
#     return render(request, 'home.html')
