"""System checks de segurança do projeto.

Rodam em `manage.py check` (e no `migrate` do deploy), tornando visível uma
configuração perigosa sem bloquear o deploy (nível Warning).
"""
from django.conf import settings
from django.core.checks import Warning, register


@register()
def field_encryption_key_configured(app_configs, **kwargs):
    """Em produção, a chave de criptografia de PII precisa estar definida.

    Sem ela, os campos sensíveis (telefone, nascimento) ficariam sem criptografia
    — e, com o fail-closed em core.encryption, o app recusa manipulá-los.
    """
    if getattr(settings, 'DEBUG', False):
        return []
    if getattr(settings, 'FIELD_ENCRYPTION_KEY', ''):
        return []
    return [
        Warning(
            'FIELD_ENCRYPTION_KEY não está definida em produção (DEBUG=False).',
            hint='Defina FIELD_ENCRYPTION_KEY no ambiente (chave Fernet base64 de 32 bytes). '
                 'Sem ela, operações com PII falham (fail-closed).',
            id='core.W001',
        )
    ]
