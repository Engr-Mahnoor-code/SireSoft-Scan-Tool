from django.contrib import admin
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.views.decorators.cache import never_cache
from .forms import LoginForm, RegisterForm


@never_cache
def login_view(request):
    if request.user.is_authenticated:
        return redirect('/')
    registered = False
    # Set by csrf_failure when a stale copy of this page was submitted.
    expired = request.session.pop('form_expired', False)
    if request.method == 'POST':
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            login(request, form.get_user())
            return redirect(request.GET.get('next', '/'))
    else:
        # Set by a sign-up that just finished, so the new user lands here
        # with their address already filled in.
        email = request.session.pop('registered_email', '')
        registered = bool(email)
        form = LoginForm(request, initial={'username': email})
    return render(request, 'accounts/login.html',
                  {'form': form, 'registered': registered,
                   'expired': expired})


@never_cache
def register_view(request):
    if request.user.is_authenticated:
        return redirect('/')
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            request.session['registered_email'] = user.email
            return redirect('accounts:login')
    else:
        form = RegisterForm()
    return render(request, 'accounts/register.html', {'form': form})


@login_required
def logout_view(request):
    logout(request)
    return redirect('/auth/login/')


def csrf_failure(request, reason=''):
    """
    Recover from a stale form instead of showing Django's bare 403 page.

    It happens when an old copy of a form is sent again - the back button,
    "Confirm Form Resubmission", or signing in from a second tab - after the
    security token has changed. Someone already signed in simply carries on;
    anyone else gets a fresh login page with a short note.
    """
    if request.user.is_authenticated:
        return redirect('/')
    request.session['form_expired'] = True
    return redirect('accounts:login')


def admin_login(request):
    """
    Django Administration's login, minus the red "not authorized" box.

    Django shows that box when someone signed in to the app as an ordinary
    user opens /admin/. Only the admin may use it, so that visitor is signed
    out and sees a clean login form for the admin account instead.
    """
    if request.user.is_authenticated and not request.user.is_staff:
        logout(request)
        return redirect(request.get_full_path())
    return admin.site.login(request)
