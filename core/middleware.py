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
