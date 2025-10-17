from django.shortcuts import render
from django.contrib.auth.decorators import login_required

@login_required
def report_list(request):
    context = {
        'section': 'reports'
    }
    return render(request, 'reports/report_list.html', context)
