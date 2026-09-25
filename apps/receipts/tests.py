import shutil
import tempfile

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.http import Http404
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from . import views
from .models import Receipt

MEDIA_ROOT = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=MEDIA_ROOT)
class ReceiptFileTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA_ROOT, ignore_errors=True)

    def setUp(self):
        self.owner = User.objects.create_user('owner', password='pw-12345')
        self.other = User.objects.create_user('other', password='pw-12345')
        self.receipt = Receipt.objects.create(
            user=self.owner,
            file=SimpleUploadedFile('r.png', b'\x89PNG fake'),
            content_type='image/png',
            status=Receipt.STATUS_SUCCESS,
            extracted_data={'insights': ['x']},
        )
        self.url = reverse('receipts:file', args=[self.receipt.pk])

    # Pages that render a template are called directly: the test client's
    # template instrumentation crashes on Django 5.1 under Python 3.14.
    def call(self, view, user):
        request = RequestFactory().get('/')
        request.user = user
        return view(request, pk=self.receipt.pk)

    def test_owner_gets_the_file_inline(self):
        self.client.login(username='owner', password='pw-12345')
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'image/png')
        self.assertTrue(response['Content-Disposition'].startswith('inline'))
        self.assertEqual(b''.join(response.streaming_content), b'\x89PNG fake')

    def test_other_user_gets_404(self):
        with self.assertRaises(Http404):
            self.call(views.receipt_file, self.other)

    def test_anonymous_is_sent_to_login(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)

    def test_unknown_type_is_downloaded_not_rendered(self):
        self.receipt.content_type = 'text/html'
        self.receipt.save()
        self.client.login(username='owner', password='pw-12345')
        response = self.client.get(self.url)
        self.assertEqual(response['Content-Type'], 'application/octet-stream')
        self.assertTrue(response['Content-Disposition'].startswith('attachment'))

    def test_missing_file_is_404(self):
        self.receipt.file.storage.delete(self.receipt.file.name)
        with self.assertRaises(Http404):
            self.call(views.receipt_file, self.owner)

    def test_detail_page_shows_the_image(self):
        response = self.call(views.detail, self.owner)
        self.assertContains(response, 'Receipt Image')
        preview = reverse('receipts:preview', args=[self.receipt.pk])
        self.assertContains(response, f'<img src="{preview}"')


@override_settings(MEDIA_ROOT=MEDIA_ROOT)
class ReceiptVisibilityTests(TestCase):
    """Staff see every receipt; anyone else sees only their own."""

    def setUp(self):
        self.alice = User.objects.create_user('alice', password='pw-12345')
        self.bob = User.objects.create_user('bob', password='pw-12345')
        self.admin = User.objects.create_user(
            'boss', password='pw-12345', is_staff=True)
        self.alice_receipt = self.make(self.alice, 'Alice Mart')
        self.bob_receipt = self.make(self.bob, 'Bob Store')

    def make(self, user, vendor):
        return Receipt.objects.create(
            user=user, vendor_name=vendor,
            file=SimpleUploadedFile('r.png', b'img'), content_type='image/png',
            status=Receipt.STATUS_SUCCESS, extracted_data={'insights': []})

    def page(self, view, user, **kwargs):
        request = RequestFactory().get('/')
        request.user = user
        return view(request, **kwargs)

    def test_user_history_lists_only_their_receipts(self):
        response = self.page(views.history, self.alice)
        self.assertContains(response, 'Alice Mart')
        self.assertNotContains(response, 'Bob Store')
        self.assertNotContains(response, 'Uploaded By')

    def test_admin_history_lists_everyones_receipts(self):
        response = self.page(views.history, self.admin)
        self.assertContains(response, 'Alice Mart')
        self.assertContains(response, 'Bob Store')
        self.assertContains(response, 'Uploaded By')

    def test_user_cannot_open_another_users_receipt_or_file(self):
        for view in (views.detail, views.receipt_file):
            with self.assertRaises(Http404):
                self.page(view, self.alice, pk=self.bob_receipt.pk)

    def test_admin_can_open_any_receipt_and_file(self):
        detail = self.page(views.detail, self.admin, pk=self.bob_receipt.pk)
        self.assertContains(detail, 'Bob Store')
        file = self.page(views.receipt_file, self.admin, pk=self.bob_receipt.pk)
        self.assertEqual(file.status_code, 200)

    def test_api_list_is_scoped_by_role(self):
        self.client.login(username='alice', password='pw-12345')
        ids = [r['id'] for r in self.client.get('/api/receipts/').json()]
        self.assertEqual(ids, [self.alice_receipt.pk])

        self.client.login(username='boss', password='pw-12345')
        ids = {r['id'] for r in self.client.get('/api/receipts/').json()}
        self.assertEqual(ids, {self.alice_receipt.pk, self.bob_receipt.pk})

    def test_api_detail_hides_other_users_receipt(self):
        self.client.login(username='alice', password='pw-12345')
        url = f'/api/receipts/{self.bob_receipt.pk}/'
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.login(username='boss', password='pw-12345')
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_api_file_link_is_the_protected_view(self):
        self.client.login(username='alice', password='pw-12345')
        data = self.client.get(f'/api/receipts/{self.alice_receipt.pk}/').json()
        self.assertTrue(data['file'].endswith(
            reverse('receipts:file', args=[self.alice_receipt.pk])))
        self.assertNotIn('/media/', data['file'])


def make_pdf_with_image():
    """A4 page with a title and one 400x300 picture, like a saved screenshot."""
    import pymupdf
    picture = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 400, 300), 0)
    picture.clear_with(200)
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((200, 60), 'Receipt Image', fontsize=24)
    page.insert_image(pymupdf.Rect(100, 100, 300, 250), pixmap=picture)
    data = doc.tobytes()
    doc.close()
    return data


@override_settings(MEDIA_ROOT=MEDIA_ROOT)
class ReceiptPreviewTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user('owner', password='pw-12345')
        self.other = User.objects.create_user('other', password='pw-12345')

    def make(self, data, name, content_type):
        return Receipt.objects.create(
            user=self.owner, file=SimpleUploadedFile(name, data),
            content_type=content_type, status=Receipt.STATUS_SUCCESS)

    def preview(self, receipt, user):
        request = RequestFactory().get('/')
        request.user = user
        return views.receipt_preview(request, pk=receipt.pk)

    def test_pdf_is_shown_as_just_its_picture(self):
        import pymupdf
        receipt = self.make(make_pdf_with_image(), 'r.pdf', 'application/pdf')
        response = self.preview(receipt, self.owner)
        self.assertEqual(response['Content-Type'], 'image/png')
        png = pymupdf.Pixmap(response.content)
        # Cropped to the picture (4:3), not the whole portrait page.
        self.assertAlmostEqual(png.width / png.height, 4 / 3, places=1)
        self.assertEqual(png.width, 400)

    def test_image_is_served_as_is(self):
        receipt = self.make(b'img-bytes', 'r.png', 'image/png')
        response = self.preview(receipt, self.owner)
        self.assertEqual(b''.join(response.streaming_content), b'img-bytes')

    def test_other_user_cannot_preview(self):
        receipt = self.make(make_pdf_with_image(), 'r.pdf', 'application/pdf')
        with self.assertRaises(Http404):
            self.preview(receipt, self.other)

    def test_broken_pdf_is_404_not_500(self):
        receipt = self.make(b'not a pdf', 'r.pdf', 'application/pdf')
        with self.assertRaises(Http404):
            self.preview(receipt, self.owner)
