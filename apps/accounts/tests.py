from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse

class AuthenticationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testpass123')
        self.client = Client()
    
    def test_login_page_renders(self):
        response = self.client.get(reverse('accounts:login'))
        self.assertEqual(response.status_code, 200)
    
    def test_login_valid_credentials(self):
        response = self.client.post(reverse('accounts:login'), {
            'username': 'testuser',
            'password': 'testpass123'
        })
        self.assertRedirects(response, '/', fetch_redirect_response=False)
    
    def test_login_invalid_credentials(self):
        response = self.client.post(reverse('accounts:login'), {
            'username': 'testuser',
            'password': 'wrongpassword'
        })
        self.assertEqual(response.status_code, 200)
        form = response.context['form']
        self.assertTrue(form.errors)
        self.assertIn('Please enter a correct username and password.', str(form.errors))
    
    def test_logout(self):
        self.client.login(username='testuser', password='testpass123')
        response = self.client.post(reverse('accounts:logout'))
        self.assertRedirects(response, reverse('accounts:login'), fetch_redirect_response=False)
    
    def test_logout_requires_post(self):
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('accounts:logout'))
        self.assertEqual(response.status_code, 405)
    
    def test_dashboard_requires_auth(self):
        response = self.client.get('/')
        self.assertRedirects(response, f"{reverse('accounts:login')}?next=/", fetch_redirect_response=False)
    
    def test_no_registration_url(self):
        response = self.client.get('/register/')
        self.assertEqual(response.status_code, 404)
        response = self.client.get('/signup/')
        self.assertEqual(response.status_code, 404)
    
    def test_password_change_requires_auth(self):
        response = self.client.get(reverse('accounts:password_change'))
        self.assertRedirects(response, f"{reverse('accounts:login')}?next={reverse('accounts:password_change')}", fetch_redirect_response=False)
    
    def test_password_change_works(self):
        self.client.login(username='testuser', password='testpass123')
        response = self.client.post(reverse('accounts:password_change'), {
            'old_password': 'testpass123',
            'new_password1': 'newpass123!@#',
            'new_password2': 'newpass123!@#'
        })
        self.assertRedirects(response, reverse('accounts:password_change_done'), fetch_redirect_response=False)
    
    def test_csrf_enforced(self):
        csrf_client = Client(enforce_csrf_checks=True)
        response = csrf_client.post(reverse('accounts:login'), {
            'username': 'testuser',
            'password': 'testpass123'
        })
        self.assertEqual(response.status_code, 403)
