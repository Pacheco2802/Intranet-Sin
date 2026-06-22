from pathlib import Path
import dj_database_url
from decouple import config

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = config('SECRET_KEY')
DEBUG = config('DEBUG', default=False, cast=bool)
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost,127.0.0.1').split(',')
CSRF_TRUSTED_ORIGINS = [
    o.strip() for o in config('CSRF_TRUSTED_ORIGINS', default='').split(',') if o.strip()
]

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'storages',
    'core',
    'comunicados',
    'mensagens',
    'kanban',
    'atendimento',
    'agenda',
    'consultas',
    'financeiro',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'core.middleware.LGPDConsentMiddleware',
    'core.middleware.DiretorScopeMiddleware',
    'core.middleware.AuditMiddleware',
]

ROOT_URLCONF = 'intranet.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'core.context_processors.global_context',
            ],
        },
    },
]

WSGI_APPLICATION = 'intranet.wsgi.application'

DATABASES = {
    'default': dj_database_url.config(
        default=f'sqlite:///{BASE_DIR / "db.sqlite3"}',
        conn_max_age=600,
    )
}

AUTH_USER_MODEL = 'core.CustomUser'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 8}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'pt-br'
TIME_ZONE = 'America/Sao_Paulo'
USE_I18N = True
USE_TZ = True

# ── Arquivos estáticos ────────────────────────────────────────────────────────
STATIC_URL = '/static/'
_static_dir = BASE_DIR / 'static'
STATICFILES_DIRS = [_static_dir] if _static_dir.exists() else []
STATIC_ROOT = BASE_DIR / 'staticfiles'

STORAGES = {
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
    },
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
}

# ── Arquivos de mídia (Railway Object Storage em produção) ───────────────────
if config('USE_S3', default=False, cast=bool):
    STORAGES['default'] = {
        'BACKEND': 'storages.backends.s3boto3.S3Boto3Storage',
    }
    AWS_ACCESS_KEY_ID       = config('AWS_ACCESS_KEY_ID')
    AWS_SECRET_ACCESS_KEY   = config('AWS_SECRET_ACCESS_KEY')
    AWS_STORAGE_BUCKET_NAME = config('AWS_STORAGE_BUCKET_NAME')
    AWS_S3_ENDPOINT_URL     = config('AWS_S3_ENDPOINT_URL')
    AWS_S3_REGION_NAME      = config('AWS_S3_REGION_NAME', default='auto')
    AWS_S3_CUSTOM_DOMAIN    = config('AWS_S3_CUSTOM_DOMAIN', default=None)
    AWS_DEFAULT_ACL         = None
    AWS_S3_FILE_OVERWRITE   = False
    AWS_QUERYSTRING_AUTH    = True
    AWS_QUERYSTRING_EXPIRE  = 3600  # link válido por 1 hora
    MEDIA_URL = (
        f'https://{AWS_S3_CUSTOM_DOMAIN}/'
        if AWS_S3_CUSTOM_DOMAIN
        else f'{AWS_S3_ENDPOINT_URL}/{AWS_STORAGE_BUCKET_NAME}/'
    )
else:
    MEDIA_URL  = '/media/'
    MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Chave de criptografia simétrica para campos sensíveis (CPF, telefone)
# Deve ser uma chave Fernet de 32 bytes em base64. Gere com:
#   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
FIELD_ENCRYPTION_KEY = config('FIELD_ENCRYPTION_KEY', default='')

AUTHENTICATION_BACKENDS = [
    'core.backends.EmailBackend',
    'django.contrib.auth.backends.ModelBackend',
]

LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/login/'

SESSION_COOKIE_AGE = 28800
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_HTTPONLY = True

CSRF_COOKIE_HTTPONLY = True
X_FRAME_OPTIONS = 'DENY'
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True

# ── Segurança adicional em produção ──────────────────────────────────────────
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000  # 1 ano
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

# ── NextQS — Gestão de Filas ─────────────────────────────────────────────────
NEXTQS_API_BASE        = 'https://api.nextqs.com'
NEXTQS_API_KEY         = config('NEXTQS_API_KEY', default='')
NEXTQS_SYSTEM_AGENT_ID = config('NEXTQS_SYSTEM_AGENT_ID', default='')
NEXTQS_SERVICE_DESK    = config('NEXTQS_SERVICE_DESK', default='68963e077804cac0600bfcc2')
NEXTQS_KIOSK_ID        = config('NEXTQS_KIOSK_ID', default='6878fd1f4a7dcacce60bf687')
NEXTQS_QUEUES = {
    'P': {'id': '69fcebfed8b1da6f24097e97', 'label': 'Previdenciário'},
    'T': {'id': '69fceca7f5a07c100b05d99c', 'label': 'Trabalhista'},
    'A': {'id': '69fcecd3f5a07c100b05d9a3', 'label': 'Andamento de Processo'},
    'M': {'id': '6878f94166fd09b66604af9b', 'label': 'Médico do Trabalho', 'service_desk_id': '6878fa784a7dcacce60bf671'},
}

# ── Limites de upload ────────────────────────────────────────────────────────
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10 MB — rejeita body acima disso antes de parsear
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024   # 5 MB — acima disso usa temp disk em vez de RAM
