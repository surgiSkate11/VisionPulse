
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from apps.security.forms.configuration import SettingsForm
from apps.security.components.sidebar_menu_mixin import SidebarMenuMixin

@login_required
def settings_view(request):
    user = request.user
    if request.method == 'POST':
        form = SettingsForm(request.POST, instance=user)
        if form.is_valid():
            form.save()
            return redirect('security:settings')
    else:
        form = SettingsForm(instance=user)
    context = SidebarMenuMixin().get_context_data(context={'settings_form': form, 'user': user}, request=request)
    return render(request, 'security/profile/settings.html', context)
