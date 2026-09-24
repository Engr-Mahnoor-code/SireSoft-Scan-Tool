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
        self.assertContains(response, 'SireSoft ReceiptIQ Tool')
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

    def test_wrong_password_names_email_and_password(self):
        response = self.client.post(
            self.url, {'username': 'yasir@example.com', 'password': 'nope'})
        self.assertContains(
            response,
            'The email address and/or password you specified are not correct.')

    def test_shared_email_does_not_pick_an_account(self):
        User.objects.create_user(
            'other', email='yasir@example.com', password='s3cret-pass')
        response = self.client.post(
            self.url, {'username': 'yasir@example.com', 'password': 's3cret-pass'})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('_auth_user_id', self.client.session)
