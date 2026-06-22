from django.shortcuts import redirect
from django.urls import reverse


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
