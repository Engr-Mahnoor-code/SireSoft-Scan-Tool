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


@override_settings(MEDIA_ROOT=MEDIA_ROOT)
class ReceiptEditTests(TestCase):
    """Owner and staff can correct a scan; nobody else can touch it."""

    def setUp(self):
        self.owner = User.objects.create_user('owner', password='pw-12345')
        self.other = User.objects.create_user('other', password='pw-12345')
        self.admin = User.objects.create_user(
            'boss', password='pw-12345', is_staff=True)
        self.receipt = Receipt.objects.create(
            user=self.owner, vendor_name='Orders', date='27 May, 2020',
            total_amount=26.06, file=SimpleUploadedFile('r.png', b'img'),
            content_type='image/png', status=Receipt.STATUS_SUCCESS,
            extracted_data={
                'establishment': {'name': 'Orders', 'date': '27 May, 2020',
                                  'time': '9:41', 'address': 'Lexington'},
                'items': [
                    {'name': 'Stout', 'quantity': 2, 'unit_price': 19.0,
                     'total': 38.0},
                    {'name': 'Budweiser', 'quantity': 1, 'unit_price': 1.73,
                     'total': 1.73},
                ],
                'bill_summary': {'subtotal': 23.06, 'grand_total': 26.06,
                                 'payment_method': 'Apple pay'},
                'insights': ['Paid with Apple pay.'],
                'details': [{'label': 'Invoice No.', 'value': 'INV-1'},
                            {'label': 'Table', 'value': '4'}],
                'extra_key': 'kept',
            })
        self.url = reverse('receipts:edit', args=[self.receipt.pk])

    def payload(self, **overrides):
        data = {
            'est-name': 'Ocean Reach Pub', 'est-date': '27 May, 2020',
            'est-time': '6:00 PM', 'est-address': '1633 Hampton Meadows',
            'details-TOTAL_FORMS': '3', 'details-INITIAL_FORMS': '2',
            'details-MIN_NUM_FORMS': '0', 'details-MAX_NUM_FORMS': '100',
            'details-0-label': 'Invoice No.', 'details-0-value': 'INV-9',
            'details-1-label': 'Table', 'details-1-value': '4',
            'details-1-DELETE': 'on',
            'details-2-label': 'GSTIN', 'details-2-value': ' 33AAQ ',
            'items-TOTAL_FORMS': '3', 'items-INITIAL_FORMS': '2',
            'items-MIN_NUM_FORMS': '0', 'items-MAX_NUM_FORMS': '200',
            'items-0-name': 'Oatmeal Stout', 'items-0-quantity': '2',
            'items-0-unit_price': '9.5', 'items-0-total': '19',
            'items-1-name': 'Budweiser', 'items-1-quantity': '1',
            'items-1-unit_price': '1.73', 'items-1-total': '1.73',
            'items-1-DELETE': 'on',
            'items-2-name': 'Stone Peak', 'items-2-quantity': '1',
            'items-2-unit_price': '2.33', 'items-2-total': '2.33',
            'bill-subtotal': '23.06', 'bill-tax': '', 'bill-discount': '',
            'bill-tip': '', 'bill-grand_total': '26.06',
            'bill-payment_method': 'Apple Pay',
            'notes-insights': 'Paid with Apple Pay.\n\n  Delivered.  ',
        }
        data.update(overrides)
        return data

    def page(self, user, method='get', data=None):
        # Rendered through the view: the test client's template
        # instrumentation crashes on Django 5.1 under Python 3.14.
        factory = RequestFactory()
        request = factory.post('/', data) if method == 'post' else factory.get('/')
        request.user = user
        request._dont_enforce_csrf_checks = True
        return views.edit(request, pk=self.receipt.pk)

    def test_detail_page_has_edit_button(self):
        request = RequestFactory().get('/')
        request.user = self.owner
        response = views.detail(request, pk=self.receipt.pk)
        self.assertContains(response, f'href="{self.url}"')

    def test_form_is_filled_from_the_scan(self):
        response = self.page(self.owner)
        self.assertContains(response, 'value="Orders"')
        self.assertContains(response, 'value="Budweiser"')
        self.assertContains(response, 'value="INV-1"')
        self.assertContains(response, 'Paid with Apple pay.')

    def test_owner_saves_corrections(self):
        self.client.login(username='owner', password='pw-12345')
        response = self.client.post(self.url, self.payload())
        self.assertRedirects(
            response, reverse('receipts:detail', args=[self.receipt.pk]),
            fetch_redirect_response=False)

        self.receipt.refresh_from_db()
        data = self.receipt.extracted_data
        self.assertEqual(data['establishment']['name'], 'Ocean Reach Pub')
        self.assertEqual(data['establishment']['time'], '6:00 PM')
        self.assertEqual([i['name'] for i in data['items']],
                         ['Oatmeal Stout', 'Stone Peak'])
        self.assertEqual(data['items'][0]['unit_price'], 9.5)
        self.assertEqual(data['bill_summary']['tax'], 0.0)
        self.assertEqual(data['bill_summary']['payment_method'], 'Apple Pay')
        self.assertEqual(data['insights'],
                         ['Paid with Apple Pay.', 'Delivered.'])
        self.assertEqual(data['extra_key'], 'kept')
        self.assertEqual(data['details'], [
            {'label': 'Invoice No.', 'value': 'INV-9'},
            {'label': 'GSTIN', 'value': '33AAQ'},
        ])
        # History reads these columns, so they follow the edit.
        self.assertEqual(self.receipt.vendor_name, 'Ocean Reach Pub')
        self.assertEqual(self.receipt.total_amount, 26.06)
        self.assertEqual(self.receipt.edited_by, self.owner)
        self.assertIsNotNone(self.receipt.edited_at)

    def test_admin_can_edit_anyones_receipt(self):
        self.client.login(username='boss', password='pw-12345')
        response = self.client.post(
            self.url, self.payload(**{'bill-grand_total': '30'}))
        self.assertEqual(response.status_code, 302)
        self.receipt.refresh_from_db()
        self.assertEqual(self.receipt.total_amount, 30.0)
        self.assertEqual(self.receipt.edited_by, self.admin)

    def test_other_user_cannot_open_or_save(self):
        with self.assertRaises(Http404):
            self.page(self.other)
        with self.assertRaises(Http404):
            self.page(self.other, 'post', self.payload())
        self.receipt.refresh_from_db()
        self.assertEqual(self.receipt.vendor_name, 'Orders')

    def test_anonymous_is_sent_to_login(self):
        response = self.client.post(self.url, self.payload())
        self.assertEqual(response.status_code, 302)
        self.assertIn('/auth/login/', response['Location'])

    def test_bad_number_keeps_the_old_data(self):
        response = self.page(self.owner, 'post',
                             self.payload(**{'bill-grand_total': 'abc'}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Enter a number.')
        self.receipt.refresh_from_db()
        self.assertEqual(self.receipt.vendor_name, 'Orders')
        self.assertIsNone(self.receipt.edited_at)

    def test_unfinished_scan_cannot_be_edited(self):
        self.receipt.status = Receipt.STATUS_PROCESSING
        self.receipt.save()
        with self.assertRaises(Http404):
            self.page(self.owner)

    def test_edit_links_on_history_and_every_detail_card(self):
        request = RequestFactory().get('/')
        request.user = self.owner
        self.assertContains(views.history(request), f'href="{self.url}"')
        detail = views.detail(request, pk=self.receipt.pk)
        self.assertContains(detail, 'Edit Receipt')
        for anchor in ('#id_est-address', '#items', '#bill',
                       '#id_notes-insights'):
            self.assertContains(detail, f'href="{self.url}{anchor}"')


@override_settings(MEDIA_ROOT=MEDIA_ROOT)
class CorrectedCopyAndDeleteTests(TestCase):
    """Saving an edit draws a corrected picture; delete removes everything."""

    def setUp(self):
        self.owner = User.objects.create_user(
            'owner', email='owner@example.com', password='pw-12345')
        self.other = User.objects.create_user('other', password='pw-12345')
        self.admin = User.objects.create_user(
            'boss', password='pw-12345', is_staff=True)
        self.receipt = Receipt.objects.create(
            user=self.owner, vendor_name='Zetran', total_amount=10.0,
            file=SimpleUploadedFile('scan.png', b'original-scan-bytes'),
            content_type='image/png', status=Receipt.STATUS_SUCCESS,
            extracted_data={
                'establishment': {'name': 'Zetran', 'address': 'Old Street'},
                'items': [{'name': 'Phone', 'quantity': 1,
                           'unit_price': 10.0, 'total': 10.0}],
                'bill_summary': {'grand_total': 10.0},
                'insights': [],
            })

    def request(self, user, method='get', data=None):
        # Views are called directly: the test client's template
        # instrumentation crashes on Django 5.1 under Python 3.14, and would
        # break the corrected-copy drawing, which renders a template.
        from django.contrib.messages.storage.fallback import FallbackStorage
        from django.contrib.sessions.backends.db import SessionStore
        factory = RequestFactory()
        request = factory.post('/', data) if method == 'post' else factory.get('/')
        request.user = user
        request.session = SessionStore()
        request._messages = FallbackStorage(request)
        request._dont_enforce_csrf_checks = True
        return request

    def save_edit(self, user, address):
        data = {
            'est-name': 'Zetran', 'est-date': '', 'est-time': '',
            'est-address': address,
            'details-TOTAL_FORMS': '1', 'details-INITIAL_FORMS': '0',
            'details-MIN_NUM_FORMS': '0', 'details-MAX_NUM_FORMS': '100',
            'details-0-label': 'Invoice No.', 'details-0-value': 'BIL-00160',
            'items-TOTAL_FORMS': '1', 'items-INITIAL_FORMS': '1',
            'items-MIN_NUM_FORMS': '0', 'items-MAX_NUM_FORMS': '200',
            'items-0-name': 'Phone', 'items-0-quantity': '1',
            'items-0-unit_price': '10', 'items-0-total': '10',
            'bill-grand_total': '10', 'notes-insights': '',
        }
        response = views.edit(self.request(user, 'post', data),
                              pk=self.receipt.pk)
        self.assertEqual(response.status_code, 302)
        self.receipt.refresh_from_db()

    def test_edit_draws_a_corrected_png_and_keeps_the_scan(self):
        import pymupdf
        self.save_edit(self.owner, 'Gulistan-e-Jauhar')
        self.assertTrue(self.receipt.corrected_file)
        png = pymupdf.Pixmap(self.receipt.corrected_file.read())
        self.assertGreater(png.width, 500)
        # The upload itself is untouched.
        self.receipt.file.open('rb')
        self.assertEqual(self.receipt.file.read(), b'original-scan-bytes')
        self.receipt.file.close()

    def test_corrected_copy_shows_the_edited_values(self):
        from django.template.loader import render_to_string
        self.receipt.extracted_data['establishment']['address'] = 'Gulistan-e-Jauhar'
        self.receipt.edited_by = self.owner
        html = render_to_string('receipts/corrected_receipt.html', {
            'receipt': self.receipt,
            'establishment': self.receipt.extracted_data['establishment'],
            'items': self.receipt.extracted_data['items'],
            'bill': self.receipt.extracted_data['bill_summary'],
        })
        self.assertIn('Gulistan-e-Jauhar', html)
        self.assertIn('CORRECTED COPY', html)
        self.assertIn('owner@example.com', html)

    def test_a_second_edit_replaces_the_old_copy(self):
        self.save_edit(self.owner, 'First')
        first = self.receipt.corrected_file.name
        storage = self.receipt.corrected_file.storage
        self.save_edit(self.owner, 'Second')
        self.assertTrue(storage.exists(self.receipt.corrected_file.name))
        if first != self.receipt.corrected_file.name:
            self.assertFalse(storage.exists(first))

    def test_corrected_copy_is_private_to_owner_and_staff(self):
        self.save_edit(self.owner, 'Gulistan-e-Jauhar')
        response = views.receipt_corrected(self.request(self.admin),
                                           pk=self.receipt.pk)
        self.assertEqual(response['Content-Type'], 'image/png')
        with self.assertRaises(Http404):
            views.receipt_corrected(self.request(self.other),
                                    pk=self.receipt.pk)

    def test_detail_and_history_show_the_corrected_copy(self):
        self.save_edit(self.owner, 'Gulistan-e-Jauhar')
        corrected = reverse('receipts:corrected', args=[self.receipt.pk])
        detail = views.detail(self.request(self.owner), pk=self.receipt.pk)
        self.assertContains(detail, 'Original scan')
        self.assertContains(detail, corrected)
        history = views.history(self.request(self.owner))
        self.assertContains(history, corrected)

    def test_delete_asks_first(self):
        response = views.delete(self.request(self.owner), pk=self.receipt.pk)
        self.assertContains(response, 'This cannot be undone.')
        self.assertTrue(Receipt.objects.filter(pk=self.receipt.pk).exists())

    def test_owner_deletes_receipt_and_both_files(self):
        self.save_edit(self.owner, 'Gulistan-e-Jauhar')
        storage = self.receipt.file.storage
        files = [self.receipt.file.name, self.receipt.corrected_file.name]
        response = views.delete(self.request(self.owner, 'post'),
                                pk=self.receipt.pk)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], reverse('receipts:history'))
        self.assertFalse(Receipt.objects.filter(pk=self.receipt.pk).exists())
        for name in files:
            self.assertFalse(storage.exists(name))

    def test_admin_can_delete_anyones_receipt(self):
        views.delete(self.request(self.admin, 'post'), pk=self.receipt.pk)
        self.assertFalse(Receipt.objects.filter(pk=self.receipt.pk).exists())

    def test_other_user_cannot_delete(self):
        with self.assertRaises(Http404):
            views.delete(self.request(self.other, 'post'), pk=self.receipt.pk)
        self.assertTrue(Receipt.objects.filter(pk=self.receipt.pk).exists())


class ExtractionDetailsTests(TestCase):
    """The scan's "details" list is cleaned like the rest of its reply."""

    def test_details_keep_labelled_pairs_only(self):
        from .services import _normalise
        data = _normalise({'details': [
            {'label': 'Invoice No.', 'value': 'INV-1'},
            {'label': 'Empty', 'value': ''},
            'not a pair',
            {'label': 'PO', 'value': 147},
        ]})
        self.assertEqual(data['details'], [
            {'label': 'Invoice No.', 'value': 'INV-1'},
            {'label': 'PO', 'value': '147'},
        ])

    def test_details_given_as_a_mapping_are_accepted(self):
        from .services import _normalise
        data = _normalise({'details': {'Due Date': '11-07-2020'}})
        self.assertEqual(data['details'],
                         [{'label': 'Due Date', 'value': '11-07-2020'}])

    def test_missing_details_become_an_empty_list(self):
        from .services import _normalise
        self.assertEqual(_normalise({})['details'], [])
