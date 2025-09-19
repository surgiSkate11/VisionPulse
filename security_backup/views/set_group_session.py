from django.views import View
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

class SetGroupSessionView(View):
    @method_decorator(csrf_exempt)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def post(self, request, *args, **kwargs):
        group_id = request.POST.get('group_id')
        if group_id:
            request.session['group_id'] = group_id  # Unifica la clave con la usada en MenuModule
            return JsonResponse({'status': 'ok'})
        return JsonResponse({'status': 'error', 'message': 'No group_id provided'}, status=400)
