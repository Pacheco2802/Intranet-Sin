from django.core.exceptions import ValidationError

ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx', 'xls', 'xlsx', 'jpg', 'jpeg', 'png', 'gif', 'zip', 'txt'}
MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10 MB


def validate_file_extension(value):
    ext = value.name.rsplit('.', 1)[-1].lower() if '.' in value.name else ''
    if ext not in ALLOWED_EXTENSIONS:
        raise ValidationError(
            f'Extensão ".{ext}" não permitida. Permitidas: {", ".join(sorted(ALLOWED_EXTENSIONS))}'
        )


def validate_file_size(value):
    if value.size > MAX_UPLOAD_SIZE:
        raise ValidationError(
            f'O arquivo excede o limite de {MAX_UPLOAD_SIZE // (1024 * 1024)} MB.'
        )
