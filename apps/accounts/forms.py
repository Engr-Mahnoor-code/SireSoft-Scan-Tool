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
    """
    Sign-up by email and password only.

    People sign in with their email, so asking for a username as well was one
    more thing to invent and forget. The email doubles as the username, capped
    at the username column's 150 characters.
    """

    email = forms.EmailField(
        label='Email',
        max_length=150,
        widget=forms.EmailInput(
            attrs={'class': 'form-input', 'autocomplete': 'email',
                   'placeholder': 'Email address'})
    )

    class Meta:
        model = User
        fields = ('email',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        placeholders = {'password1': 'Password',
                        'password2': 'Confirm password'}
        self.fields['password2'].label = 'Confirm Password'
        for name, field in self.fields.items():
            field.widget.attrs['class'] = 'form-input'
            if name in placeholders:
                field.widget.attrs['placeholder'] = placeholders[name]
                field.widget.attrs['autocomplete'] = 'new-password'
            # The rules list is long; the error names the one that failed.
            field.help_text = ''

    def clean_email(self):
        # Sign-in by email only works while each address names one account,
        # so a second sign-up must not be able to take someone's address
        # (the admin's included) and lock them out of email login.
        email = self.cleaned_data['email'].strip().lower()
        if (User.objects.filter(email__iexact=email).exists()
                or User.objects.filter(username__iexact=email).exists()):
            raise forms.ValidationError(
                'An account with this email already exists.')
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.username = self.cleaned_data['email']
        if commit:
            user.save()
        return user


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
