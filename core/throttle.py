"""Throttle de tentativas de login (anti brute-force / credential-stuffing).

Conta falhas por IP e por e-mail-alvo no cache. O limite por e-mail (mais alto)
barra ataques distribuídos numa conta sem facilitar lockout-DoS; o por IP barra
o caso comum de um host tentando muitas senhas.

Observação: com o cache padrão (LocMemCache) os contadores são por processo e
zeram a cada deploy. Com um cache compartilhado (Redis via REDIS_URL) o limite
passa a valer globalmente.
"""
from django.core.cache import cache

from .middleware import AuditMiddleware

LOGIN_IP_MAX = 10
LOGIN_EMAIL_MAX = 15
LOGIN_FAIL_WINDOW = 900  # 15 min


def _keys(request, email):
    ip = AuditMiddleware.get_client_ip(request) or 'unknown'
    keys = [(f'lf_ip:{ip}', LOGIN_IP_MAX)]
    if email:
        keys.append((f'lf_em:{email.strip().lower()}', LOGIN_EMAIL_MAX))
    return keys


def is_blocked(request, email=None):
    return any(cache.get(k, 0) >= limit for k, limit in _keys(request, email))


def record_failure(request, email=None):
    for k, _limit in _keys(request, email):
        cache.set(k, cache.get(k, 0) + 1, LOGIN_FAIL_WINDOW)


def clear(request, email=None):
    for k, _limit in _keys(request, email):
        cache.delete(k)
