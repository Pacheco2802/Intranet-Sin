"""
Criptografia simétrica (Fernet/AES-128-CBC + HMAC-SHA256) para campos sensíveis.

Os valores são cifrados antes de persistir e decifrados ao carregar — transparente
para o resto da aplicação. A chave vem de settings.FIELD_ENCRYPTION_KEY.

Se FIELD_ENCRYPTION_KEY estiver vazia (desenvolvimento sem .env), os campos são
armazenados em plaintext com aviso — nunca use em produção sem a chave configurada.
"""
import base64
import logging
from datetime import date

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.db import models

logger = logging.getLogger(__name__)

_fernet: Fernet | None = None
_warned = False


def _get_fernet() -> Fernet | None:
    global _fernet, _warned
    if _fernet:
        return _fernet
    key = getattr(settings, 'FIELD_ENCRYPTION_KEY', '')
    if not key:
        if not _warned:
            logger.warning(
                'FIELD_ENCRYPTION_KEY não configurada — campos sensíveis '
                'serão armazenados em plaintext. Configure antes de ir para produção.'
            )
            _warned = True
        return None
    try:
        _fernet = Fernet(key.encode() if isinstance(key, str) else key)
    except Exception:
        logger.error('FIELD_ENCRYPTION_KEY inválida. Verifique o valor no .env.')
        return None
    return _fernet


def encrypt_value(value: str) -> str:
    if not value:
        return value
    f = _get_fernet()
    if f is None:
        return value
    return f.encrypt(value.encode()).decode()


def decrypt_value(value: str) -> str:
    if not value:
        return value
    f = _get_fernet()
    if f is None:
        return value
    try:
        return f.decrypt(value.encode()).decode()
    except (InvalidToken, Exception):
        # Valor ainda em plaintext (migração em andamento) — retorna como está
        return value


# ── Campos customizados ──────────────────────────────────────────────────────

class EncryptedCharField(models.TextField):
    """CharField que cifra antes de salvar e decifra ao ler."""

    def __init__(self, *args, **kwargs):
        # Ignora max_length para o banco (TextField não tem limite)
        kwargs.pop('max_length', None)
        super().__init__(*args, **kwargs)

    def from_db_value(self, value, expression, connection):
        return decrypt_value(value) if value else value

    def get_prep_value(self, value):
        prepped = super().get_prep_value(value)
        return encrypt_value(prepped) if prepped else prepped

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        return name, path, args, kwargs


class EncryptedDateField(models.TextField):
    """DateField que cifra o valor ISO-8601 antes de salvar."""

    def from_db_value(self, value, expression, connection):
        if not value:
            return None
        raw = decrypt_value(value)
        try:
            return date.fromisoformat(raw)
        except (ValueError, TypeError):
            return None

    def get_prep_value(self, value):
        if value is None:
            return None
        if isinstance(value, date):
            value = value.isoformat()
        return encrypt_value(str(value))

    def to_python(self, value):
        if isinstance(value, date) or value is None:
            return value
        raw = decrypt_value(value)
        try:
            return date.fromisoformat(raw)
        except (ValueError, TypeError):
            return None

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        return name, path, args, kwargs
