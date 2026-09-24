from django import forms
from django.contrib.auth.forms import (
    AuthenticationForm, PasswordResetForm, SetPasswordForm, UserCreationForm)
from django.contrib.auth.models import User


class LoginForm(AuthenticationForm):
    # Labelled "Email", but a username still signs in: accounts made before
    # login by email existed only know theirs.
    username = forms.CharField(
        label='Email',
        widget=forms.TextInput(
            attrs={'class': 'form-input', 'autocomplete': 'username',
                   'placeholder': 'Email address'})
    )
    password = forms.CharField(
        widget=forms.PasswordInput(
            attrs={'class': 'form-input',
                   'autocomplete': 'current-password',
                   'placeholder': 'Password'})
    )

    error_messages = {
        **AuthenticationForm.error_messages,
        'invalid_login': ('The email address and/or password you specified '
                          'are not correct.'),
    }

    def clean_username(self):
        value = self.cleaned_data['username'].strip()
        if '@' in value:
            # Email isn't unique on User, so only a single match can be
            # trusted to name the account.
            matches = list(User.objects.filter(email__iexact=value)[:2])
            if len(matches) == 1:
                return matches[0].get_username()
        return value


class RegisterForm(UserCreationForm):
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(
            attrs={'class': 'form-input', 'placeholder': 'Email'})
    )

    class Meta:
        model = User
        fields = ('username', 'email', 'password1', 'password2')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            field.widget.attrs.setdefault('class', 'form-input')
            if field_name == 'username':
                field.widget.attrs['placeholder'] = 'Username'
            elif field_name == 'password1':
                field.widget.attrs['placeholder'] = 'Password'
            elif field_name == 'password2':
                field.widget.attrs['placeholder'] = 'Confirm Password'


class ResetPasswordForm(PasswordResetForm):
    email = forms.EmailField(
        label='Email',
        max_length=254,
        widget=forms.EmailInput(
            attrs={'class': 'form-input', 'autocomplete': 'email',
                   'placeholder': 'Email address'})
    )


class NewPasswordForm(SetPasswordForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        placeholders = {'new_password1': 'New password',
                        'new_password2': 'Confirm new password'}
        for name, field in self.fields.items():
            field.widget.attrs['class'] = 'form-input'
            field.widget.attrs['placeholder'] = placeholders.get(name, '')
            # The rules list is long; the error names the one that failed.
            field.help_text = ''
