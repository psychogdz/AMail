from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from apps.mailboxes.models import Category, EmailAddress


@login_required
def dashboard(request):
    user_addresses = EmailAddress.objects.filter(user=request.user)
    context = {
        'stats': {
            'total_addresses': user_addresses.count(),
            'active_addresses': user_addresses.filter(is_active=True).count(),
            'total_emails': 0,
            'unread_emails': 0,
            'total_categories': Category.objects.filter(user=request.user).count(),
        }
    }
    return render(request, 'core/dashboard.html', context)
