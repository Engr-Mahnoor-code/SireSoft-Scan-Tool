from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse


class LoginViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            'yasir', email='yasir@example.com', password='s3cret-pass')
        self.url = reverse('accounts:login')

    def test_page_shows_receiptiq_banner(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'SireSoft Scan Tool')
        self.assertContains(response, 'Leader in Innovation')
        self.assertNotContains(response, 'Project Management')

    def test_signs_in_with_email(self):
        response = self.client.post(
            self.url, {'username': 'Yasir@Example.com', 'password': 's3cret-pass'})
        self.assertRedirects(response, '/', fetch_redirect_response=False)
        self.assertEqual(int(self.client.session['_auth_user_id']), self.user.pk)

    def test_signs_in_with_username(self):
        response = self.client.post(
            self.url, {'username': 'yasir', 'password': 's3cret-pass'})
        self.assertRedirects(response, '/', fetch_redirect_response=False)

    def test_wrong_password_shows_no_error_line(self):
        response = self.client.post(
            self.url, {'username': 'yasir@example.com', 'password': 'nope'})
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(
            response,
            'The email address and/or password you specified are not correct.')

    def test_shared_email_does_not_pick_an_account(self):
        User.objects.create_user(
            'other', email='yasir@example.com', password='s3cret-pass')
        response = self.client.post(
            self.url, {'username': 'yasir@example.com', 'password': 's3cret-pass'})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('_auth_user_id', self.client.session)


class RegisterTests(TestCase):
    """Sign up with email and password, then sign in with the same pair."""

    url = '/auth/register/'

    def post(self, email='New@Example.com', password='Str0ng-pass-99',
             confirm=None):
        return self.client.post(self.url, {
            'email': email, 'password1': password,
            'password2': confirm or password})

    def login_page(self):
        # Rendered through the view, not the test client: the client's
        # template instrumentation crashes on Django 5.1 under Python 3.14.
        from django.contrib.auth.models import AnonymousUser
        from django.test import RequestFactory
        from . import views
        request = RequestFactory().get('/auth/login/')
        request.user = AnonymousUser()
        request.session = self.client.session
        return views.login_view(request)

    def test_sign_up_creates_user_and_sends_to_login(self):
        response = self.post()
        self.assertRedirects(response, '/auth/login/',
                             fetch_redirect_response=False)
        user = User.objects.get(email='new@example.com')
        self.assertEqual(user.username, 'new@example.com')
        self.assertFalse(user.is_staff)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_login_page_confirms_and_prefills_email(self):
        self.post()
        response = self.login_page()
        self.assertContains(response, 'Account created.')
        self.assertContains(response, 'value="new@example.com"')

    def test_new_user_can_sign_in_with_email_and_password(self):
        self.post()
        response = self.client.post('/auth/login/', {
            'username': 'new@example.com', 'password': 'Str0ng-pass-99'})
        self.assertRedirects(response, '/', fetch_redirect_response=False)

    def test_taken_email_is_rejected(self):
        User.objects.create_user('someone', email='new@example.com',
                                 password='x')
        from .forms import RegisterForm
        form = RegisterForm(data={'email': 'NEW@example.com',
                                  'password1': 'Str0ng-pass-99',
                                  'password2': 'Str0ng-pass-99'})
        self.assertFalse(form.is_valid())
        self.assertIn('email', form.errors)

    def test_mismatched_passwords_are_rejected(self):
        from .forms import RegisterForm
        form = RegisterForm(data={'email': 'a@example.com',
                                  'password1': 'Str0ng-pass-99',
                                  'password2': 'Other-pass-99'})
        self.assertFalse(form.is_valid())
        self.assertFalse(User.objects.filter(email='a@example.com').exists())


class EnsureAdminTests(TestCase):
    """manage.py ensure_admin makes the admin account match .env."""

    def run_command(self, **env):
        from unittest import mock
        from django.core.management import call_command
        with mock.patch.dict('os.environ', env, clear=False):
            call_command('ensure_admin', stdout=__import__('io').StringIO())

    def test_creates_admin_who_can_sign_in_both_ways(self):
        from django.contrib.auth import authenticate
        self.run_command(ADMIN_USERNAME='admin', ADMIN_EMAIL='admin@siresoft.com',
                         ADMIN_PASSWORD='Pakistan12345')
        user = User.objects.get(username='admin')
        self.assertTrue(user.is_staff and user.is_superuser)
        self.assertEqual(user.email, 'admin@siresoft.com')
        self.assertIsNotNone(authenticate(username='admin', password='Pakistan12345'))

    def test_repairs_an_existing_admin(self):
        User.objects.create_user('admin', email='old@gmail.com', password='old')
        self.run_command(ADMIN_USERNAME='admin', ADMIN_EMAIL='admin@siresoft.com',
                         ADMIN_PASSWORD='Pakistan12345')
        user = User.objects.get(username='admin')
        self.assertEqual(user.email, 'admin@siresoft.com')
        self.assertTrue(user.check_password('Pakistan12345'))
        self.assertEqual(User.objects.count(), 1)

    def test_refuses_without_a_password(self):
        from django.core.management.base import CommandError
        with self.assertRaises(CommandError):
            self.run_command(ADMIN_EMAIL='admin@siresoft.com', ADMIN_PASSWORD='')

    def test_refuses_an_email_owned_by_someone_else(self):
        from django.core.management.base import CommandError
        User.objects.create_user('mahnoor', email='admin@siresoft.com', password='x')
        with self.assertRaises(CommandError):
            self.run_command(ADMIN_USERNAME='admin', ADMIN_EMAIL='admin@siresoft.com',
                             ADMIN_PASSWORD='Pakistan12345')
