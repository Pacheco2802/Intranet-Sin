"""Testes de regressão de segurança.

Cobrem as invariantes verificadas no pentest: criptografia fail-closed, backend de
autenticação, throttle de login, open-redirect e controle de acesso (IDOR).

Rodar:  python manage.py test core.test_security
"""
from decimal import Decimal

from cryptography.fernet import Fernet
from django.contrib.auth import authenticate, get_user_model
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

User = get_user_model()
PWD = 'SenhaBemForte#2026'


def make_user(email, **kw):
    kw.setdefault('is_active', True)
    kw.setdefault('is_approved', True)
    kw.setdefault('lgpd_consent', True)  # evita o redirect do LGPDConsentMiddleware
    return User.objects.create_user(
        username=email.split('@')[0], email=email, password=PWD, **kw
    )


class EncryptionFailClosedTests(TestCase):
    def tearDown(self):
        import core.encryption as enc
        enc._fernet = None  # não vaza estado entre testes

    def test_roundtrip_with_key(self):
        import core.encryption as enc
        with override_settings(DEBUG=False, FIELD_ENCRYPTION_KEY=Fernet.generate_key().decode()):
            enc._fernet = None
            ct = enc.encrypt_value('11999998888')
            self.assertNotEqual(ct, '11999998888')
            self.assertEqual(enc.decrypt_value(ct), '11999998888')

    def test_fail_closed_in_prod_without_key(self):
        import core.encryption as enc
        with override_settings(DEBUG=False, FIELD_ENCRYPTION_KEY=''):
            enc._fernet = None
            with self.assertRaises(ImproperlyConfigured):
                enc.encrypt_value('segredo')

    def test_plaintext_only_in_dev(self):
        import core.encryption as enc
        with override_settings(DEBUG=True, FIELD_ENCRYPTION_KEY=''):
            enc._fernet = None
            self.assertEqual(enc.encrypt_value('x'), 'x')


class EmailBackendTests(TestCase):
    def test_unknown_email_returns_none(self):
        self.assertIsNone(authenticate(username='naoexiste@x.com', password='qualquer'))

    def test_valid_credentials_case_insensitive(self):
        u = make_user('user@x.com')
        self.assertEqual(authenticate(username='USER@x.com', password=PWD), u)

    def test_wrong_password_returns_none(self):
        make_user('user2@x.com')
        self.assertIsNone(authenticate(username='user2@x.com', password='errada'))

    def test_inactive_user_cannot_authenticate(self):
        make_user('inativo@x.com', is_active=False)
        self.assertIsNone(authenticate(username='inativo@x.com', password=PWD))


class LoginThrottleTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_blocks_after_max_attempts(self):
        from core.throttle import LOGIN_IP_MAX
        make_user('vitima@x.com')
        url = reverse('core:login')
        for _ in range(LOGIN_IP_MAX):
            self.client.post(url, {'email': 'vitima@x.com', 'password': 'errada'})
        resp = self.client.post(url, {'email': 'vitima@x.com', 'password': 'errada'})
        self.assertContains(resp, 'Muitas tentativas')

    def test_success_clears_counter(self):
        make_user('ok@x.com')
        url = reverse('core:login')
        for _ in range(3):
            self.client.post(url, {'email': 'ok@x.com', 'password': 'errada'})
        resp = self.client.post(url, {'email': 'ok@x.com', 'password': PWD})
        self.assertEqual(resp.status_code, 302)  # login OK
        from core.throttle import is_blocked
        self.assertFalse(is_blocked(RequestFactory().post('/', REMOTE_ADDR='127.0.0.1'), 'ok@x.com'))


class OpenRedirectTests(TestCase):
    def test_safe_next_rejects_external(self):
        from financeiro.views import _safe_next
        req = RequestFactory().post('/financeiro/x/', {'next': 'https://evil.example/phish'})
        self.assertEqual(_safe_next(req, '/fallback/'), '/fallback/')

    def test_safe_next_rejects_protocol_relative(self):
        from financeiro.views import _safe_next
        req = RequestFactory().post('/financeiro/x/', {'next': '//evil.example'})
        self.assertEqual(_safe_next(req, '/fallback/'), '/fallback/')

    def test_safe_next_allows_internal(self):
        from financeiro.views import _safe_next
        req = RequestFactory().post('/financeiro/x/', {'next': '/financeiro/reembolsos/1/'})
        self.assertEqual(_safe_next(req, '/fallback/'), '/financeiro/reembolsos/1/')


class MensagensIDORTests(TestCase):
    def test_non_participant_forbidden(self):
        from mensagens.models import Conversation
        a, b = make_user('a@x.com'), make_user('b@x.com')
        conv = Conversation.objects.create(is_group=False, created_by=a)
        conv.participants.add(a)
        self.client.force_login(b)
        resp = self.client.get(reverse('mensagens:conversation', kwargs={'pk': conv.pk}))
        self.assertEqual(resp.status_code, 403)

    def test_participant_allowed(self):
        from mensagens.models import Conversation
        a = make_user('a2@x.com')
        conv = Conversation.objects.create(is_group=False, created_by=a)
        conv.participants.add(a)
        self.client.force_login(a)
        resp = self.client.get(reverse('mensagens:conversation', kwargs={'pk': conv.pk}))
        self.assertEqual(resp.status_code, 200)


class FinanceiroIDORTests(TestCase):
    def test_reembolso_detail_non_owner_forbidden(self):
        from financeiro.models import Reembolso
        a, b = make_user('dono@x.com'), make_user('outro@x.com')
        r = Reembolso.objects.create(solicitante=a, titulo='Táxi', valor=Decimal('42.00'))
        self.client.force_login(b)
        resp = self.client.get(reverse('financeiro:reembolso_detail', kwargs={'pk': r.pk}))
        self.assertEqual(resp.status_code, 403)

    def test_reembolso_detail_owner_ok(self):
        from financeiro.models import Reembolso
        a = make_user('dono2@x.com')
        r = Reembolso.objects.create(solicitante=a, titulo='Táxi', valor=Decimal('42.00'))
        self.client.force_login(a)
        resp = self.client.get(reverse('financeiro:reembolso_detail', kwargs={'pk': r.pk}))
        self.assertEqual(resp.status_code, 200)
