"""Throttle das rotas públicas de triagem (sem login).

Mesmo padrão do core/throttle.py: contadores no cache com janela deslizante.
Duas dimensões:
  - por IP: total de envios/tentativas (barra spam de um host);
  - por alvo (senha ou código): falhas de vínculo (barra brute-force de CPF
    contra uma senha vista no display, ou enumeração de códigos).

Com REDIS_URL configurado os limites valem globalmente entre workers; com
LocMemCache são por processo (suficiente para conter abuso básico).
"""
from django.core.cache import cache

from core.middleware import AuditMiddleware

IP_MAX = 10       # envios/tentativas por IP na janela
ALVO_MAX = 5      # falhas por senha/código alvo na janela
WINDOW = 900      # 15 min


def _ip(request):
    return AuditMiddleware.get_client_ip(request) or 'unknown'


def ip_blocked(request):
    return cache.get(f'tri_ip:{_ip(request)}', 0) >= IP_MAX


def record_ip(request):
    key = f'tri_ip:{_ip(request)}'
    cache.set(key, cache.get(key, 0) + 1, WINDOW)


def alvo_blocked(chave):
    return cache.get(f'tri_alvo:{chave}', 0) >= ALVO_MAX


def record_alvo(chave):
    key = f'tri_alvo:{chave}'
    cache.set(key, cache.get(key, 0) + 1, WINDOW)


def clear_alvo(chave):
    cache.delete(f'tri_alvo:{chave}')
