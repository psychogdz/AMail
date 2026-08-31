from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count
from .models import Category, EmailAddress, get_default_domain
from .forms import CategoryForm, EmailAddressForm, MoveAddressForm

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
def address_create(request):
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
        form = EmailAddressForm(request.user)
    return render(request, 'mailboxes/address_create.html', {'form': form, 'email_domain': get_default_domain()})

@login_required
def address_detail(request, pk):
    address = get_object_or_404(EmailAddress, pk=pk, user=request.user)
    return render(request, 'mailboxes/address_detail.html', {'address': address})

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
@require_POST
def address_delete(request, pk):
    address = get_object_or_404(EmailAddress, pk=pk, user=request.user)
    address_str = address.address
    address.delete()
    messages.success(request, f"Address {address_str} deleted successfully.")
    return redirect('mailboxes:address_list')
