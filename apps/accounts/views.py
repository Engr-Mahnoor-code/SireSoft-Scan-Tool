from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from .forms import LoginForm, RegisterForm


def login_view(request):
    if request.user.is_authenticated:
        return redirect('/')
    registered = False
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
                  {'form': form, 'registered': registered})


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
