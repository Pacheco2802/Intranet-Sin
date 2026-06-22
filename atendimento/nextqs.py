import requests
from django.conf import settings


# NextQS limita ticket_customer_name a 30 caracteres (HTTP 400 acima disso).
NOME_MAX = 30


def _headers():
    return {
        'Authorization': f'Bearer {settings.NEXTQS_API_KEY}',
        'Content-Type': 'application/json',
    }


def _nome_display(at):
    """Nome do filiado dentro do limite do NextQS (30 chars), com prefixo de preferencial."""
    nome = at.nome_filiado or ''
    if at.is_preferencial:
        return f'PREFERENCIAL - {nome}'[:NOME_MAX]
    return nome[:NOME_MAX]


def _erro_request(exc):
    """Extrai a mensagem real do NextQS (corpo da resposta) quando houver, em vez do genérico."""
    resp = getattr(exc, 'response', None)
    if resp is not None:
        try:
            data = resp.json()
            msg = data.get('error') or data.get('message') or resp.text
        except ValueError:
            msg = resp.text[:300]
        return f'{resp.status_code}: {msg}'
    return str(exc)


def emitir_senha(at):
    """Cria ticket no NextQS e aciona a impressora térmica. Salva numero_senha no atendimento."""
    if not settings.NEXTQS_API_KEY:
        return False, 'NEXTQS_API_KEY não configurado.'
    queue_info = settings.NEXTQS_QUEUES.get(at.nextqs_fila)
    if not queue_info:
        return False, 'Fila não reconhecida.'
    nome_display = _nome_display(at)
    payload = {
        'queue_id': queue_info['id'],
        'service_desk_id': settings.NEXTQS_SERVICE_DESK,
        'kiosk_id': settings.NEXTQS_KIOSK_ID,
        'customer_name': nome_display,
        'priority': at.is_preferencial,
        'support_fields': [{
            'label': 'CPF',
            'value': at.cpf,
            'input': 'input',
            'type': 'text',
            'required': False,
            'sensible': True,
            'internal': False,
        }],
    }
    try:
        r = requests.post(
            f'{settings.NEXTQS_API_BASE}/v1/organization/token',
            json=payload,
            headers=_headers(),
            timeout=8,
        )
        r.raise_for_status()
        data = r.json()
        item = data[0] if isinstance(data, list) else data
        at.numero_senha = str(item.get('ticket_number', ''))
        at.save(update_fields=['numero_senha'])
        return True, item.get('ticket', at.numero_senha)
    except requests.RequestException as exc:
        return False, _erro_request(exc)


def _service_desk(queue_info):
    """Retorna o service_desk_id da fila, com fallback para o global."""
    return queue_info.get('service_desk_id') or settings.NEXTQS_SERVICE_DESK


def chamar_senha(at, agent_id):
    """Chama a senha no display. Usa o service_desk_id da fila se configurado."""
    if not settings.NEXTQS_API_KEY:
        return False, 'NEXTQS_API_KEY não configurado.'
    queue_info = settings.NEXTQS_QUEUES.get(at.nextqs_fila)
    if not queue_info:
        return False, 'Fila não reconhecida.'
    nome_display = _nome_display(at)
    payload = {
        'queue_id': queue_info['id'],
        'service_desk_id': _service_desk(queue_info),
        'ticket': at.numero_senha,
        'alpha': at.nextqs_fila,
        'customer_name': nome_display,
        'priority': at.is_preferencial,
        'agent_id': agent_id,
    }
    try:
        r = requests.post(
            f'{settings.NEXTQS_API_BASE}/v1/organization/actions/directcall',
            json=payload,
            headers=_headers(),
            timeout=8,
        )
        r.raise_for_status()
        return True, 'OK'
    except requests.RequestException as exc:
        return False, _erro_request(exc)


def cancelar_senha(at, agent_id):
    """Remove ticket da fila NextQS via directcall + noshow."""
    if not settings.NEXTQS_API_KEY:
        return False, 'NEXTQS_API_KEY não configurado.'
    queue_info = settings.NEXTQS_QUEUES.get(at.nextqs_fila)
    if not queue_info:
        return False, 'Fila não reconhecida.'
    try:
        r = requests.post(
            f'{settings.NEXTQS_API_BASE}/v1/organization/actions/directcall',
            json={
                'queue_id': queue_info['id'],
                'service_desk_id': _service_desk(queue_info),
                'ticket': at.numero_senha,
                'alpha': at.nextqs_fila,
                'customer_name': _nome_display(at),
                'agent_id': agent_id,
            },
            headers=_headers(),
            timeout=8,
        )
        r.raise_for_status()
        service_origin_id = r.json().get('service_origin_id')
        if not service_origin_id:
            return False, 'service_origin_id não retornado pelo NextQS.'
        r2 = requests.post(
            f'{settings.NEXTQS_API_BASE}/v1/organization/actions/noshow',
            json={
                'service_origin_id': service_origin_id,
                'agent_id': agent_id,
                'service_desk_id': _service_desk(queue_info),
            },
            headers=_headers(),
            timeout=8,
        )
        r2.raise_for_status()
        return True, 'OK'
    except requests.RequestException as exc:
        return False, _erro_request(exc)
