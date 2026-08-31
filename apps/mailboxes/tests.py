from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from apps.mailboxes.models import Category, EmailAddress


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
        # Form should have errors — duplicate name for same user
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
        # View redirects to HTTP_REFERER or address_list
        self.assertEqual(response.status_code, 302)
        addr.refresh_from_db()
        self.assertFalse(addr.is_active)

    def test_address_toggle_other_user(self):
        addr2 = EmailAddress.objects.create(user=self.user2, local_part='toggle2')
        response = self.client.post(reverse('mailboxes:address_toggle', args=[addr2.pk]))
        self.assertEqual(response.status_code, 404)
        addr2.refresh_from_db()
        self.assertTrue(addr2.is_active)

    def test_address_delete(self):
        addr = EmailAddress.objects.create(user=self.user1, local_part='todelete')
        response = self.client.post(reverse('mailboxes:address_delete', args=[addr.pk]))
        self.assertRedirects(response, reverse('mailboxes:address_list'), fetch_redirect_response=False)
        self.assertFalse(EmailAddress.objects.filter(pk=addr.pk).exists())

    def test_address_delete_other_user(self):
        addr2 = EmailAddress.objects.create(user=self.user2, local_part='protected')
        response = self.client.post(reverse('mailboxes:address_delete', args=[addr2.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(EmailAddress.objects.filter(pk=addr2.pk).exists())

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
