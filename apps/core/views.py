from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from apps.mailboxes.models import Category, EmailAddress, EmailMessage


@login_required
def dashboard(request):
    user_addresses = EmailAddress.objects.filter(user=request.user)
    user_emails = EmailMessage.objects.filter(
        email_address__user=request.user
    ).select_related('email_address', 'email_address__category')
    
    recent_emails = user_emails[:8]

    context = {
        'stats': {
            'total_addresses': user_addresses.count(),
            'active_addresses': user_addresses.filter(is_active=True).count(),
            'total_emails': user_emails.count(),
            'unread_emails': user_emails.filter(is_read=False).count(),
            'total_categories': Category.objects.filter(user=request.user).count(),
        },
        'recent_emails': recent_emails,
    }
    return render(request, 'core/dashboard.html', context)
