from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User


class LoginForm(AuthenticationForm):
    username = forms.CharField(
        widget=forms.TextInput(
            attrs={'class': 'form-input', 'placeholder': 'Username'})
    )
    password = forms.CharField(
        widget=forms.PasswordInput(
            attrs={'class': 'form-input', 'placeholder': 'Password'})
    )


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
