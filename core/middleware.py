from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse


# Content-Security-Policy. Mantida permissiva para scripts (a app usa muito JS
# inline + Alpine, que exigem 'unsafe-inline'/'unsafe-eval'), mas trava clickjacking,
# base-uri, form-action e objetos. Vai em Report-Only por padrão para não quebrar
# nada; defina CSP_ENFORCE=True no ambiente quando quiser aplicar de fato
# (idealmente após migrar os scripts inline para nonces).
CSP_POLICY = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net https://unpkg.com; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
    "img-src 'self' data: https:; "
    "font-src 'self' https://fonts.gstatic.com data:; "
    "connect-src 'self'; "
    "object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
)


class ContentSecurityPolicyMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.enforce = getattr(settings, 'CSP_ENFORCE', False)

    def __call__(self, request):
        response = self.get_response(request)
        header = 'Content-Security-Policy' if self.enforce else 'Content-Security-Policy-Report-Only'
        response.setdefault(header, CSP_POLICY)
        return response


LGPD_EXEMPT_URLS = [
    '/login/',
    '/logout/',
    '/lgpd/consentimento/',
    '/lgpd/politica/',
    '/admin/',
    '/static/',
    '/media/',
]


def _is_exempt(path):
    return any(path.startswith(url) for url in LGPD_EXEMPT_URLS)


class LGPDConsentMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (
            request.user.is_authenticated
            and not request.user.lgpd_consent
            and not _is_exempt(request.path)
        ):
            return redirect(reverse('core:lgpd_consent'))
        return self.get_response(request)


# Prefixos que o diretor "restrito" pode acessar. Tudo o mais é bloqueado.
DIRETOR_ALLOWED_URLS = [
    '/financeiro/diretoria/',    # lançar atividade, minhas atividades, detalhe, aprovar/rejeitar
    '/financeiro/reembolsos/',   # reembolsos (mantido)
    '/perfil/',                  # perfil + alterar senha
    '/notificacoes/',            # sino/badge (poll do base.html) + avisos de aprovação/pagamento
    '/lgpd/',                    # consentimento/política/exportar
    '/login/',
    '/logout/',
    '/static/',
    '/media/',
]


class DiretorScopeMiddleware:
    """Restringe o diretor 'puro' às abas de atividade/reembolso. Bloqueio real por URL
    (não só esconder o menu): qualquer rota fora da allowlist redireciona para
    'Minhas atividades'."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user
        if (
            user.is_authenticated
            and user.is_diretor_restrito
            and not any(request.path.startswith(url) for url in DIRETOR_ALLOWED_URLS)
        ):
            return redirect('financeiro:atividade_list')
        return self.get_response(request)


class AdminLoginThrottleMiddleware:
    """Aplica o mesmo throttle de brute-force ao login do Django admin
    (/admin/login/), que usa view própria fora do login_view da aplicação."""

    ADMIN_LOGIN_PATH = '/admin/login/'

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from django.http import HttpResponse
        from . import throttle

        is_login_post = request.method == 'POST' and request.path == self.ADMIN_LOGIN_PATH
        if is_login_post and throttle.is_blocked(request):
            return HttpResponse(
                'Muitas tentativas de acesso. Aguarde alguns minutos e tente novamente.',
                status=429,
            )
        response = self.get_response(request)
        if is_login_post:
            # 302 = login OK (admin redireciona); qualquer outro = falhou → conta
            if response.status_code == 302:
                throttle.clear(request)
            else:
                throttle.record_failure(request)
        return response


class AuditMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    @staticmethod
    def get_client_ip(request):
        x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded:
            return x_forwarded.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR')
