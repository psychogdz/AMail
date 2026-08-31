from django.test import TestCase, TransactionTestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from django.db import connection
from django.core.management import call_command
import re
import os
import tempfile
from email.message import EmailMessage as PyEmailMessage
from apps.mailboxes.models import Category, EmailAddress, EmailMessage
from apps.mailboxes.generator import (
    generate_random_local_part,
    generate_raw_candidate,
    GENERATOR_STYLES,
)
from scripts.ingest_mail import (
    ingest,
    parse_email_message,
    EX_OK,
    EX_NOUSER,
    EX_UNAVAILABLE,
)


class CategoryTests(TestCase):
    def setUp(self):
        self.user1 = User.objects.create_user(username='user1', password='password')
        self.user2 = User.objects.create_user(username='user2', password='password')
        self.client = Client()
        self.client.login(username='user1', password='password')
        self.category1 = Category.objects.create(user=self.user1, name='Personal')

    def test_category_list_requires_auth(self):
        self.client.logout()
        url = reverse('mailboxes:category_list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)

    def test_category_list_shows_own(self):
        Category.objects.create(user=self.user2, name='Work')
        response = self.client.get(reverse('mailboxes:category_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Personal')
        self.assertNotContains(response, 'Work')

    def test_category_create(self):
        response = self.client.post(reverse('mailboxes:category_create'), {'name': 'Newsletters'})
        self.assertRedirects(response, reverse('mailboxes:category_list'), fetch_redirect_response=False)
        self.assertTrue(Category.objects.filter(user=self.user1, name='Newsletters').exists())

    def test_category_create_duplicate(self):
        response = self.client.post(reverse('mailboxes:category_create'), {'name': 'Personal'})
        self.assertEqual(response.status_code, 200)
        form = response.context['form']
        self.assertTrue(form.errors)

    def test_category_edit(self):
        response = self.client.post(
            reverse('mailboxes:category_edit', args=[self.category1.pk]),
            {'name': 'Updated'}
        )
        self.assertRedirects(response, reverse('mailboxes:category_list'), fetch_redirect_response=False)
        self.category1.refresh_from_db()
        self.assertEqual(self.category1.name, 'Updated')

    def test_category_edit_other_user(self):
        category2 = Category.objects.create(user=self.user2, name='Work')
        response = self.client.post(
            reverse('mailboxes:category_edit', args=[category2.pk]),
            {'name': 'Hacked'}
        )
        self.assertEqual(response.status_code, 404)
        category2.refresh_from_db()
        self.assertEqual(category2.name, 'Work')

    def test_category_delete(self):
        response = self.client.post(reverse('mailboxes:category_delete', args=[self.category1.pk]))
        self.assertRedirects(response, reverse('mailboxes:category_list'), fetch_redirect_response=False)
        self.assertFalse(Category.objects.filter(pk=self.category1.pk).exists())

    def test_category_delete_moves_addresses(self):
        cat2 = Category.objects.create(user=self.user1, name='Fallback')
        addr = EmailAddress.objects.create(user=self.user1, category=self.category1, local_part='test')
        response = self.client.post(
            reverse('mailboxes:category_delete', args=[self.category1.pk]),
            {'move_to': cat2.pk}
        )
        self.assertRedirects(response, reverse('mailboxes:category_list'), fetch_redirect_response=False)
        self.assertFalse(Category.objects.filter(pk=self.category1.pk).exists())
        addr.refresh_from_db()
        self.assertEqual(addr.category, cat2)

    def test_category_delete_uncategorizes_addresses(self):
        addr = EmailAddress.objects.create(user=self.user1, category=self.category1, local_part='orphan')
        self.client.post(reverse('mailboxes:category_delete', args=[self.category1.pk]))
        addr.refresh_from_db()
        self.assertIsNone(addr.category)

    def test_category_delete_other_user(self):
        category2 = Category.objects.create(user=self.user2, name='Work')
        response = self.client.post(reverse('mailboxes:category_delete', args=[category2.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(Category.objects.filter(pk=category2.pk).exists())


class EmailAddressTests(TestCase):
    def setUp(self):
        self.user1 = User.objects.create_user(username='user1', password='password')
        self.user2 = User.objects.create_user(username='user2', password='password')
        self.client = Client()
        self.client.login(username='user1', password='password')
        self.category1 = Category.objects.create(user=self.user1, name='Personal')

    def test_address_list_requires_auth(self):
        self.client.logout()
        url = reverse('mailboxes:address_list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)

    def test_address_list_shows_own(self):
        EmailAddress.objects.create(user=self.user1, local_part='user1test')
        EmailAddress.objects.create(user=self.user2, local_part='user2test')
        response = self.client.get(reverse('mailboxes:address_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'user1test')
        self.assertNotContains(response, 'user2test')

    def test_address_create(self):
        response = self.client.post(reverse('mailboxes:address_create'), {
            'local_part': 'netflix',
            'category': self.category1.pk
        })
        self.assertRedirects(response, reverse('mailboxes:address_list'), fetch_redirect_response=False)
        addr = EmailAddress.objects.get(user=self.user1, local_part='netflix')
        self.assertEqual(addr.category, self.category1)
        self.assertEqual(addr.domain, 'viomet.online')

    def test_address_create_no_category(self):
        response = self.client.post(reverse('mailboxes:address_create'), {
            'local_part': 'nocategory',
            'category': ''
        })
        self.assertRedirects(response, reverse('mailboxes:address_list'), fetch_redirect_response=False)
        addr = EmailAddress.objects.get(local_part='nocategory')
        self.assertIsNone(addr.category)

    def test_address_create_duplicate(self):
        EmailAddress.objects.create(user=self.user1, local_part='netflix')
        response = self.client.post(reverse('mailboxes:address_create'), {
            'local_part': 'netflix'
        })
        self.assertEqual(response.status_code, 200)
        form = response.context['form']
        self.assertTrue(form.errors.get('local_part'))

    def test_address_create_duplicate_cross_user(self):
        EmailAddress.objects.create(user=self.user2, local_part='taken')
        response = self.client.post(reverse('mailboxes:address_create'), {
            'local_part': 'taken'
        })
        self.assertEqual(response.status_code, 200)
        form = response.context['form']
        self.assertTrue(form.errors.get('local_part'))

    def test_address_create_reserved(self):
        response = self.client.post(reverse('mailboxes:address_create'), {
            'local_part': 'postmaster'
        })
        self.assertEqual(response.status_code, 200)
        form = response.context['form']
        self.assertTrue(form.errors.get('local_part'))

    def test_address_create_invalid_chars(self):
        response = self.client.post(reverse('mailboxes:address_create'), {
            'local_part': 'a b'
        })
        self.assertEqual(response.status_code, 200)
        form = response.context['form']
        self.assertTrue(form.errors.get('local_part'))

    def test_address_create_uppercase_normalized(self):
        response = self.client.post(reverse('mailboxes:address_create'), {
            'local_part': 'Netflix'
        })
        self.assertRedirects(response, reverse('mailboxes:address_list'), fetch_redirect_response=False)
        self.assertTrue(EmailAddress.objects.filter(user=self.user1, local_part='netflix').exists())
        self.assertFalse(EmailAddress.objects.filter(local_part='Netflix').exists())

    def test_address_toggle(self):
        addr = EmailAddress.objects.create(user=self.user1, local_part='toggle')
        self.assertTrue(addr.is_active)
        response = self.client.post(reverse('mailboxes:address_toggle', args=[addr.pk]))
        self.assertEqual(response.status_code, 302)
        addr.refresh_from_db()
        self.assertFalse(addr.is_active)

    def test_address_toggle_other_user(self):
        addr2 = EmailAddress.objects.create(user=self.user2, local_part='toggle2')
        response = self.client.post(reverse('mailboxes:address_toggle', args=[addr2.pk]))
        self.assertEqual(response.status_code, 404)
        addr2.refresh_from_db()
        self.assertTrue(addr2.is_active)

    def test_address_move_category(self):
        addr = EmailAddress.objects.create(user=self.user1, local_part='moveme')
        response = self.client.post(
            reverse('mailboxes:address_move', args=[addr.pk]),
            {'category': self.category1.pk}
        )
        self.assertEqual(response.status_code, 302)
        addr.refresh_from_db()
        self.assertEqual(addr.category, self.category1)

    def test_address_detail_own(self):
        addr = EmailAddress.objects.create(user=self.user1, local_part='detail')
        response = self.client.get(reverse('mailboxes:address_detail', args=[addr.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'detail@viomet.online')

    def test_address_detail_other_user(self):
        addr2 = EmailAddress.objects.create(user=self.user2, local_part='secret')
        response = self.client.get(reverse('mailboxes:address_detail', args=[addr2.pk]))
        self.assertEqual(response.status_code, 404)

    def test_address_list_filter_by_category(self):
        cat2 = Category.objects.create(user=self.user1, name='Work')
        EmailAddress.objects.create(user=self.user1, category=self.category1, local_part='personal')
        EmailAddress.objects.create(user=self.user1, category=cat2, local_part='work')

        response = self.client.get(reverse('mailboxes:address_list'), {'category': self.category1.pk})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'personal')
        self.assertNotContains(response, 'work')

    def test_address_list_pagination(self):
        for i in range(25):
            EmailAddress.objects.create(user=self.user1, local_part=f'addr{i:03d}')

        response = self.client.get(reverse('mailboxes:address_list'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['page_obj']), 20)

        response2 = self.client.get(reverse('mailboxes:address_list'), {'page': '2'})
        self.assertEqual(response2.status_code, 200)
        self.assertEqual(len(response2.context['page_obj']), 5)


class RandomGeneratorTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='genuser', password='password')
        self.client = Client()
        self.client.login(username='genuser', password='password')

    def test_generate_short_style(self):
        for _ in range(10):
            val = generate_raw_candidate(style='short')
            self.assertEqual(len(val), 5)
            self.assertTrue(re.match(r'^[a-z0-9]{5}$', val))

    def test_generate_standard_style(self):
        for _ in range(10):
            val = generate_raw_candidate(style='standard')
            self.assertEqual(len(val), 8)
            self.assertTrue(re.match(r'^[a-z0-9]{8}$', val))

    def test_generate_human_like_style(self):
        for _ in range(10):
            val = generate_raw_candidate(style='human_like')
            self.assertTrue(re.match(r'^[a-z]+[0-9]{2}$', val))

    def test_generate_random_local_part_uniqueness(self):
        generated = set()
        for _ in range(20):
            val = generate_random_local_part(style='short')
            self.assertNotIn(val, generated)
            generated.add(val)
            EmailAddress.objects.create(user=self.user, local_part=val)

    def test_generate_random_skips_existing(self):
        EmailAddress.objects.create(user=self.user, local_part='fixed1')
        val = generate_random_local_part(style='standard')
        self.assertNotEqual(val, 'fixed1')

    def test_generate_api_authenticated(self):
        for style in GENERATOR_STYLES:
            response = self.client.get(reverse('mailboxes:address_generate_random'), {'style': style})
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertTrue(data['success'])
            self.assertIn('local_part', data)
            self.assertIn('address', data)
            self.assertIn('@viomet.online', data['address'])
            self.assertEqual(data['style'], style)

    def test_generate_api_unauthenticated(self):
        self.client.logout()
        response = self.client.get(reverse('mailboxes:address_generate_random'))
        self.assertEqual(response.status_code, 302)

    def test_create_address_with_generated_local_part(self):
        gen_part = generate_random_local_part(style='human_like')
        response = self.client.post(reverse('mailboxes:address_create'), {
            'local_part': gen_part,
        })
        self.assertRedirects(response, reverse('mailboxes:address_list'), fetch_redirect_response=False)
        self.assertTrue(EmailAddress.objects.filter(user=self.user, local_part=gen_part).exists())


class AddressDeleteTests(TestCase):
    def setUp(self):
        self.user1 = User.objects.create_user(username='user1', password='password')
        self.user2 = User.objects.create_user(username='user2', password='password')
        self.client = Client()
        self.client.login(username='user1', password='password')
        self.address = EmailAddress.objects.create(user=self.user1, local_part='deltest', is_active=True)

    def test_address_delete_get_confirmation(self):
        response = self.client.get(reverse('mailboxes:address_delete', args=[self.address.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'deltest@viomet.online')
        self.assertContains(response, 'Disable Address')
        self.assertContains(response, 'Delete Address Permanently')

    def test_address_delete_post_action_delete(self):
        response = self.client.post(
            reverse('mailboxes:address_delete', args=[self.address.pk]),
            {'action': 'delete'}
        )
        self.assertRedirects(response, reverse('mailboxes:address_list'), fetch_redirect_response=False)
        self.assertFalse(EmailAddress.objects.filter(pk=self.address.pk).exists())

    def test_address_delete_post_action_disable(self):
        response = self.client.post(
            reverse('mailboxes:address_delete', args=[self.address.pk]),
            {'action': 'disable'}
        )
        self.assertRedirects(response, reverse('mailboxes:address_list'), fetch_redirect_response=False)
        self.address.refresh_from_db()
        self.assertFalse(self.address.is_active)
        self.assertTrue(EmailAddress.objects.filter(pk=self.address.pk).exists())

    def test_address_delete_other_user(self):
        addr2 = EmailAddress.objects.create(user=self.user2, local_part='protected')
        response_get = self.client.get(reverse('mailboxes:address_delete', args=[addr2.pk]))
        self.assertEqual(response_get.status_code, 404)

        response_post = self.client.post(
            reverse('mailboxes:address_delete', args=[addr2.pk]),
            {'action': 'delete'}
        )
        self.assertEqual(response_post.status_code, 404)
        self.assertTrue(EmailAddress.objects.filter(pk=addr2.pk).exists())


class MailIngestTests(TestCase):
    def setUp(self):
        self.user1 = User.objects.create_user(username='muser1', password='password')
        self.user2 = User.objects.create_user(username='muser2', password='password')
        self.client = Client()
        self.client.login(username='muser1', password='password')
        self.address1 = EmailAddress.objects.create(user=self.user1, local_part='netflix', domain='viomet.online')
        self.raw_conn = connection.connection

    def _build_email_bytes(self, to_addr, from_addr="sender@example.com", subject="Test Subject", body="Test Body", html_body=None, attachment=None):
        msg = PyEmailMessage()
        msg['To'] = to_addr
        msg['From'] = from_addr
        msg['Subject'] = subject
        msg.set_content(body)

        if html_body:
            msg.add_alternative(html_body, subtype='html')

        if attachment:
            filename, content, maintype, subtype = attachment
            msg.add_attachment(content, maintype=maintype, subtype=subtype, filename=filename)

        return msg.as_bytes()

    def test_ingest_plain_text(self):
        raw = self._build_email_bytes("netflix@viomet.online", from_addr="Netflix <info@netflix.com>", subject="Welcome!", body="Hello World")
        status = ingest(raw, conn=self.raw_conn)
        self.assertEqual(status, EX_OK)

        messages = EmailMessage.objects.filter(email_address=self.address1)
        self.assertEqual(messages.count(), 1)
        msg = messages.first()
        self.assertEqual(msg.recipient, "netflix@viomet.online")
        self.assertEqual(msg.subject, "Welcome!")
        self.assertEqual(msg.sender_name, "Netflix")
        self.assertEqual(msg.sender_email, "info@netflix.com")
        self.assertIn("Hello World", msg.body_plain)
        self.assertFalse(msg.is_read)
        self.assertFalse(msg.has_attachments)

        # Check model computed properties
        self.assertEqual(self.address1.received_count, 1)
        self.assertEqual(self.address1.unread_count, 1)

    def test_ingest_html_and_text_multipart(self):
        raw = self._build_email_bytes(
            "netflix@viomet.online",
            subject="HTML Newsletter",
            body="Plain text fallback",
            html_body="<h1>Hello HTML</h1><p>Special Offer</p>"
        )
        status = ingest(raw, conn=self.raw_conn)
        self.assertEqual(status, EX_OK)

        msg = EmailMessage.objects.get(email_address=self.address1, subject="HTML Newsletter")
        self.assertIn("Plain text fallback", msg.body_plain)
        self.assertIn("<h1>Hello HTML</h1>", msg.body_html)

    def test_ingest_with_attachments(self):
        pdf_bytes = b"%PDF-1.4 sample pdf content bytes"
        raw = self._build_email_bytes(
            "netflix@viomet.online",
            subject="Invoice attached",
            body="Please see invoice attached.",
            attachment=("invoice.pdf", pdf_bytes, "application", "pdf")
        )
        status = ingest(raw, conn=self.raw_conn)
        self.assertEqual(status, EX_OK)

        msg = EmailMessage.objects.get(email_address=self.address1, subject="Invoice attached")
        self.assertTrue(msg.has_attachments)
        self.assertEqual(len(msg.attachments_info), 1)
        self.assertEqual(msg.attachments_info[0]['name'], "invoice.pdf")
        self.assertEqual(msg.attachments_info[0]['content_type'], "application/pdf")
        self.assertEqual(msg.attachments_info[0]['size'], len(pdf_bytes))

    def test_ingest_utf8_subject_and_body(self):
        raw = self._build_email_bytes(
            "netflix@viomet.online",
            from_addr="خدمات مشتریان <support@viomet.online>",
            subject="خوش آمدید - Welcome 🚀",
            body="سلام! این یک ایمیل آزمایشی است."
        )
        status = ingest(raw, conn=self.raw_conn)
        self.assertEqual(status, EX_OK)

        msg = EmailMessage.objects.get(email_address=self.address1, recipient="netflix@viomet.online")
        self.assertIn("خوش آمدید", msg.subject)
        self.assertIn("سلام!", msg.body_plain)

    def test_ingest_unknown_recipient(self):
        raw = self._build_email_bytes("nonexistent@viomet.online", subject="Spam", body="Spam message")
        status = ingest(raw, conn=self.raw_conn)
        self.assertEqual(status, EX_NOUSER)
        self.assertFalse(EmailMessage.objects.filter(recipient="nonexistent@viomet.online").exists())

    def test_ingest_disabled_recipient(self):
        disabled_addr = EmailAddress.objects.create(user=self.user1, local_part="disabledacc", is_active=False)
        raw = self._build_email_bytes("disabledacc@viomet.online", subject="Blocked", body="Blocked message")
        status = ingest(raw, conn=self.raw_conn)
        self.assertEqual(status, EX_UNAVAILABLE)
        self.assertFalse(EmailMessage.objects.filter(email_address=disabled_addr).exists())

    def test_ingest_cli_recipient_override(self):
        raw = self._build_email_bytes("undisclosed-recipients:;", subject="BCC Message", body="Secret body")
        status = ingest(raw, cli_recipient="netflix@viomet.online", conn=self.raw_conn)
        self.assertEqual(status, EX_OK)

        msg = EmailMessage.objects.get(email_address=self.address1, subject="BCC Message")
        self.assertEqual(msg.recipient, "netflix@viomet.online")

    def test_dashboard_stats_with_received_emails(self):
        addr2 = EmailAddress.objects.create(user=self.user2, local_part='steam', domain='viomet.online')

        # user1 receives 2 emails
        raw1 = self._build_email_bytes("netflix@viomet.online", subject="Msg 1", body="Body 1")
        raw2 = self._build_email_bytes("netflix@viomet.online", subject="Msg 2", body="Body 2")
        ingest(raw1, conn=self.raw_conn)
        ingest(raw2, conn=self.raw_conn)

        # user2 receives 1 email
        raw3 = self._build_email_bytes("steam@viomet.online", subject="Msg 3", body="Body 3")
        ingest(raw3, conn=self.raw_conn)

        # user1 dashboard
        response1 = self.client.get(reverse('core:dashboard'))
        self.assertEqual(response1.status_code, 200)
        self.assertEqual(response1.context['stats']['total_emails'], 2)
        self.assertEqual(response1.context['stats']['unread_emails'], 2)

        # user2 dashboard
        self.client.login(username='muser2', password='password')
        response2 = self.client.get(reverse('core:dashboard'))
        self.assertEqual(response2.status_code, 200)
        self.assertEqual(response2.context['stats']['total_emails'], 1)
        self.assertEqual(response2.context['stats']['unread_emails'], 1)

    def test_ingest_management_command(self):
        raw = self._build_email_bytes("netflix@viomet.online", subject="CLI Ingestion", body="Ingested via manage.py")
        with tempfile.NamedTemporaryFile('wb', suffix='.eml', delete=False) as tf:
            tf.write(raw)
            temp_name = tf.name

        try:
            call_command('ingest_email', file=temp_name)
            self.assertTrue(EmailMessage.objects.filter(email_address=self.address1, subject="CLI Ingestion").exists())
        finally:
            if os.path.exists(temp_name):
                os.remove(temp_name)


class ValidationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='validator', password='password')
        self.client = Client()
        self.client.login(username='validator', password='password')

    def _create_address(self, local_part):
        return self.client.post(reverse('mailboxes:address_create'), {
            'local_part': local_part,
        })

    def test_valid_local_parts(self):
        valid = ['a', 'test', 'my-email', 'user.name', 'test123', 'a1']
        for lp in valid:
            EmailAddress.objects.filter(local_part=lp).delete()
            response = self._create_address(lp)
            self.assertRedirects(response, reverse('mailboxes:address_list'), fetch_redirect_response=False,
                                 msg_prefix=f"'{lp}' should be valid")

    def test_invalid_local_parts(self):
        invalid = ['a b', 'test@host', 'test!', '-start', '.start']
        for lp in invalid:
            response = self._create_address(lp)
            self.assertEqual(response.status_code, 200,
                             msg=f"'{lp}' should be rejected")
            form = response.context['form']
            self.assertTrue(form.errors.get('local_part'),
                            msg=f"'{lp}' should have local_part error")

    def test_reserved_addresses(self):
        for reserved in ['postmaster', 'abuse', 'admin', 'root']:
            response = self._create_address(reserved)
            self.assertEqual(response.status_code, 200,
                             msg=f"'{reserved}' should be rejected")

    def test_max_length(self):
        response = self._create_address('a' * 64)
        self.assertRedirects(response, reverse('mailboxes:address_list'), fetch_redirect_response=False)

        response = self._create_address('b' * 65)
        self.assertEqual(response.status_code, 200)
