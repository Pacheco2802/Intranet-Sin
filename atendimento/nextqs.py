import requests
from django.conf import settings


def _headers():
    return {
        'Authorization': f'Bearer {settings.NEXTQS_API_KEY}',
        'Content-Type': 'application/json',
    }


def emitir_senha(at):
    """Cria ticket no NextQS e aciona a impressora térmica. Salva numero_senha no atendimento."""
    if not settings.NEXTQS_API_KEY:
        return False, 'NEXTQS_API_KEY não configurado.'
    queue_info = settings.NEXTQS_QUEUES.get(at.nextqs_fila)
    if not queue_info:
        return False, 'Fila não reconhecida.'
    payload = {
        'queue_id': queue_info['id'],
        'service_desk_id': settings.NEXTQS_SERVICE_DESK,
        'kiosk_id': settings.NEXTQS_KIOSK_ID,
        'customer_name': at.nome_filiado[:30],
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
        return False, str(exc)


def chamar_senha(at, agent_id):
    """Chama a senha no display da recepção (Sala 14)."""
    if not settings.NEXTQS_API_KEY:
        return False, 'NEXTQS_API_KEY não configurado.'
    queue_info = settings.NEXTQS_QUEUES.get(at.nextqs_fila)
    if not queue_info:
        return False, 'Fila não reconhecida.'
    payload = {
        'queue_id': queue_info['id'],
        'service_desk_id': settings.NEXTQS_SERVICE_DESK,
        'ticket': at.numero_senha,
        'alpha': at.nextqs_fila,
        'customer_name': at.nome_filiado[:30],
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
        return False, str(exc)


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
                'service_desk_id': settings.NEXTQS_SERVICE_DESK,
                'ticket': at.numero_senha,
                'alpha': at.nextqs_fila,
                'customer_name': at.nome_filiado[:30],
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
            json={'service_origin_id': service_origin_id, 'agent_id': agent_id},
            headers=_headers(),
            timeout=8,
        )
        r2.raise_for_status()
        return True, 'OK'
    except requests.RequestException as exc:
        return False, str(exc)
