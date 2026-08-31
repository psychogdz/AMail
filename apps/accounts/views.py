from django.contrib.auth.views import LoginView, PasswordChangeView
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_POST
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.contrib import messages
from apps.core.ratelimit import ratelimit
from .forms import LoginForm


@method_decorator(ratelimit(key_prefix='login', limit=10, period=60, methods=('POST',)), name='dispatch')
class CustomLoginView(LoginView):
    form_class = LoginForm
    template_name = 'accounts/login.html'
    redirect_authenticated_user = True


@require_POST
def logout_view(request):
    logout(request)
    return redirect('accounts:login')


class CustomPasswordChangeView(PasswordChangeView):
    template_name = 'accounts/password_change.html'
    success_url = reverse_lazy('accounts:password_change_done')


@login_required
def password_change_done(request):
    messages.success(request, 'Your password was successfully updated.')
    return redirect('/')
