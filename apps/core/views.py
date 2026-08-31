from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def dashboard(request):
    context = {
        'stats': {
            'total_addresses': 0,
            'active_addresses': 0,
            'total_emails': 0,
            'unread_emails': 0,
            'total_categories': 0,
        }
    }
    return render(request, 'core/dashboard.html', context)
