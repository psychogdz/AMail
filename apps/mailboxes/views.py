import html
import re
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import JsonResponse, HttpResponse
from apps.core.ratelimit import ratelimit
from .models import Category, EmailAddress, EmailMessage, get_default_domain
from .forms import CategoryForm, EmailAddressForm, MoveAddressForm
from .generator import generate_random_local_part, GENERATOR_STYLES


@login_required
def category_list(request):
    categories = Category.objects.filter(user=request.user).annotate(
        address_count=Count('addresses')
    )
    return render(request, 'mailboxes/category_list.html', {'categories': categories})


@login_required
def category_create(request):
    if request.method == 'POST':
        form = CategoryForm(request.POST, user=request.user)
        if form.is_valid():
            category = form.save(commit=False)
            category.user = request.user
            category.save()
            messages.success(request, f"Category '{category.name}' created successfully.")
            return redirect('mailboxes:category_list')
    else:
        form = CategoryForm(user=request.user)
    return render(request, 'mailboxes/category_form.html', {'form': form})


@login_required
def category_edit(request, pk):
    category = get_object_or_404(Category, pk=pk, user=request.user)
    if request.method == 'POST':
        form = CategoryForm(request.POST, instance=category, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, f"Category '{category.name}' updated successfully.")
            return redirect('mailboxes:category_list')
    else:
        form = CategoryForm(instance=category, user=request.user)
    return render(request, 'mailboxes/category_form.html', {'form': form, 'category': category})


@login_required
def category_delete(request, pk):
    category = get_object_or_404(Category, pk=pk, user=request.user)
    if request.method == 'POST':
        move_to_id = request.POST.get('move_to')
        if move_to_id:
            target_category = get_object_or_404(Category, pk=move_to_id, user=request.user)
            category.addresses.update(category=target_category)
        else:
            category.addresses.update(category=None)
        
        category.delete()
        messages.success(request, f"Category '{category.name}' deleted successfully.")
        return redirect('mailboxes:category_list')
    
    other_categories = Category.objects.filter(user=request.user).exclude(pk=pk)
    return render(request, 'mailboxes/category_delete.html', {
        'category': category,
        'other_categories': other_categories
    })


@login_required
def address_list(request):
    queryset = EmailAddress.objects.filter(user=request.user)
    
    category_id = request.GET.get('category')
    if category_id:
        queryset = queryset.filter(category_id=category_id)
        
    paginator = Paginator(queryset, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    categories = Category.objects.filter(user=request.user)
    
    return render(request, 'mailboxes/address_list.html', {
        'page_obj': page_obj,
        'categories': categories,
        'current_category': category_id
    })


@login_required
@ratelimit(key_prefix='address_create', limit=30, period=60, methods=('POST',))
def address_create(request):
    domain = get_default_domain()
    
    if request.method == 'POST':
        form = EmailAddressForm(request.user, request.POST)
        if form.is_valid():
            address = EmailAddress.objects.create(
                user=request.user,
                local_part=form.cleaned_data['local_part'],
                category=form.cleaned_data['category']
            )
            messages.success(request, f"Email address {address.address} created successfully.")
            return redirect('mailboxes:address_list')
    else:
        initial_style = request.GET.get('style', 'standard')
        if initial_style not in GENERATOR_STYLES:
            initial_style = 'standard'
        try:
            suggested_local_part = generate_random_local_part(style=initial_style)
        except Exception:
            suggested_local_part = ''
            
        form = EmailAddressForm(request.user, initial={'local_part': request.GET.get('local_part', '')})
        
    return render(request, 'mailboxes/address_create.html', {
        'form': form,
        'email_domain': domain,
        'suggested_local_part': locals().get('suggested_local_part', ''),
        'generator_styles': GENERATOR_STYLES,
    })


@login_required
@ratelimit(key_prefix='address_generate', limit=60, period=60)
def address_generate_api(request):
    """
    JSON API endpoint for generating random email local_part candidates on demand.
    """
    style = request.GET.get('style', 'standard')
    if style not in GENERATOR_STYLES:
        style = 'standard'
        
    domain = get_default_domain()
    try:
        local_part = generate_random_local_part(style=style, domain=domain)
        return JsonResponse({
            'success': True,
            'local_part': local_part,
            'address': f"{local_part}@{domain}",
            'style': style,
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e),
        }, status=500)


@login_required
def address_detail(request, pk):
    address = get_object_or_404(EmailAddress, pk=pk, user=request.user)
    categories = Category.objects.filter(user=request.user)
    return render(request, 'mailboxes/address_detail.html', {
        'address': address,
        'categories': categories,
    })


@login_required
@require_POST
def address_toggle(request, pk):
    address = get_object_or_404(EmailAddress, pk=pk, user=request.user)
    address.is_active = not address.is_active
    address.save()
    status = "activated" if address.is_active else "deactivated"
    messages.success(request, f"Address {address.address} has been {status}.")
    return redirect(request.META.get('HTTP_REFERER', 'mailboxes:address_list'))


@login_required
@require_POST
def address_move(request, pk):
    address = get_object_or_404(EmailAddress, pk=pk, user=request.user)
    form = MoveAddressForm(request.user, request.POST)
    if form.is_valid():
        address.category = form.cleaned_data['category']
        address.save()
        messages.success(request, f"Address {address.address} moved successfully.")
    return redirect(request.META.get('HTTP_REFERER', 'mailboxes:address_list'))


@login_required
def address_delete(request, pk):
    address = get_object_or_404(EmailAddress, pk=pk, user=request.user)
    
    if request.method == 'POST':
        action = request.POST.get('action', 'delete')
        address_str = address.address
        
        if action == 'disable':
            address.is_active = False
            address.save()
            messages.success(request, f"Address {address_str} has been disabled.")
        else:
            address.delete()
            messages.success(request, f"Address {address_str} deleted successfully.")
            
        return redirect('mailboxes:address_list')
        
    return render(request, 'mailboxes/address_delete.html', {
        'address': address
    })


# ==========================================
# INBOX & EMAIL VIEWER VIEWS
# ==========================================

@login_required
def inbox_list(request):
    """
    Inbox view showing list of received emails with filtering, search, and pagination.
    """
    queryset = EmailMessage.objects.filter(email_address__user=request.user).select_related('email_address', 'email_address__category')

    # Filter by category
    category_id = request.GET.get('category')
    if category_id:
        queryset = queryset.filter(email_address__category_id=category_id)

    # Filter by specific email address
    address_id = request.GET.get('address')
    if address_id:
        queryset = queryset.filter(email_address_id=address_id)

    # Filter by read status
    status_filter = request.GET.get('status')
    if status_filter == 'unread':
        queryset = queryset.filter(is_read=False)
    elif status_filter == 'read':
        queryset = queryset.filter(is_read=True)

    # Search filter
    search_query = request.GET.get('q', '').strip()
    if search_query:
        queryset = queryset.filter(
            Q(subject__icontains=search_query) |
            Q(sender__icontains=search_query) |
            Q(sender_email__icontains=search_query) |
            Q(sender_name__icontains=search_query) |
            Q(recipient__icontains=search_query) |
            Q(body_plain__icontains=search_query)
        )

    paginator = Paginator(queryset, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    categories = Category.objects.filter(user=request.user)
    addresses = EmailAddress.objects.filter(user=request.user)
    total_unread = EmailMessage.objects.filter(email_address__user=request.user, is_read=False).count()

    return render(request, 'mailboxes/inbox.html', {
        'page_obj': page_obj,
        'categories': categories,
        'addresses': addresses,
        'current_category': category_id,
        'current_address': address_id,
        'current_status': status_filter,
        'search_query': search_query,
        'total_unread': total_unread,
    })


@login_required
def email_detail(request, pk):
    """
    Detailed email viewer. Automatically marks the email as read upon viewing.
    """
    email_obj = get_object_or_404(
        EmailMessage.objects.select_related('email_address', 'email_address__category'),
        pk=pk,
        email_address__user=request.user
    )

    if not email_obj.is_read:
        email_obj.is_read = True
        email_obj.save(update_fields=['is_read'])

    return render(request, 'mailboxes/email_detail.html', {
        'email': email_obj,
    })


@login_required
def email_html_raw(request, pk):
    """
    Renders raw email HTML inside a heavily sandboxed response.
    Applies strict Content Security Policy to prevent XSS / script execution.
    """
    email_obj = get_object_or_404(EmailMessage, pk=pk, email_address__user=request.user)
    
    html_content = email_obj.body_html.strip()
    if not html_content:
        # Fallback to escaped plain text wrapped in pre
        escaped_plain = html.escape(email_obj.body_plain)
        html_content = f"<!DOCTYPE html><html><head><meta charset='utf-8'><style>body {{ font-family: monospace; white-space: pre-wrap; padding: 16px; color: #333; background: #fff; }}</style></head><body>{escaped_plain}</body></html>"
    else:
        # Inject <base target="_blank"> so external links open safely in a new tab
        if '<head>' in html_content.lower():
            html_content = re.sub(r'(<head[^>]*>)', r'\1<base target="_blank">', html_content, count=1, flags=re.IGNORECASE)
        else:
            html_content = '<base target="_blank">' + html_content

    response = HttpResponse(html_content, content_type='text/html; charset=utf-8')
    # Strict CSP preventing any scripts or navigation hijacking
    response['Content-Security-Policy'] = "default-src 'none'; style-src 'unsafe-inline' https: http: data:; img-src data: https: http: cid:; font-src data: https: http:; media-src data: https: http:;"
    response['X-Content-Type-Options'] = 'nosniff'
    response['X-Frame-Options'] = 'SAMEORIGIN'
    return response


@login_required
@require_POST
def email_toggle_read(request, pk):
    """
    Toggle read / unread status of an individual email.
    """
    email_obj = get_object_or_404(EmailMessage, pk=pk, email_address__user=request.user)
    email_obj.is_read = not email_obj.is_read
    email_obj.save(update_fields=['is_read'])
    
    status_label = "read" if email_obj.is_read else "unread"
    messages.success(request, f"Message marked as {status_label}.")
    return redirect(request.META.get('HTTP_REFERER', 'mailboxes:inbox'))


@login_required
@require_POST
def email_delete(request, pk):
    """
    Delete an individual email.
    """
    email_obj = get_object_or_404(EmailMessage, pk=pk, email_address__user=request.user)
    subject = email_obj.subject
    email_obj.delete()
    messages.success(request, f"Message '{subject}' deleted successfully.")
    return redirect('mailboxes:inbox')


@login_required
@require_POST
def email_bulk_action(request):
    """
    Handle bulk actions: mark selected emails as read, mark as unread, or delete.
    """
    action = request.POST.get('action')
    email_ids = request.POST.getlist('selected_emails')

    if not email_ids:
        messages.warning(request, "No messages selected.")
        return redirect(request.META.get('HTTP_REFERER', 'mailboxes:inbox'))

    # Strict user isolation: filter by current user
    queryset = EmailMessage.objects.filter(id__in=email_ids, email_address__user=request.user)
    count = queryset.count()

    if action == 'mark_read':
        queryset.update(is_read=True)
        messages.success(request, f"{count} message(s) marked as read.")
    elif action == 'mark_unread':
        queryset.update(is_read=False)
        messages.success(request, f"{count} message(s) marked as unread.")
    elif action == 'delete':
        queryset.delete()
        messages.success(request, f"{count} message(s) deleted.")
    else:
        messages.error(request, "Invalid action.")

    return redirect(request.META.get('HTTP_REFERER', 'mailboxes:inbox'))
