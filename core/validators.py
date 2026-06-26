from django.core.exceptions import ValidationError

ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx', 'xls', 'xlsx', 'jpg', 'jpeg', 'png', 'gif', 'zip', 'txt'}
MAX_UPLOAD_SIZE = 5 * 1024 * 1024  # 5 MB


def validate_file_extension(value):
    ext = value.name.rsplit('.', 1)[-1].lower() if '.' in value.name else ''
    if ext not in ALLOWED_EXTENSIONS:
        nome = value.name
        ext_msg = f'sem extensão' if not ext else f'extensão ".{ext}"'
        raise ValidationError(
            f'O arquivo "{nome}" ({ext_msg}) não é aceito. '
            f'Use um dos formatos: {", ".join(sorted(ALLOWED_EXTENSIONS))}.'
        )


def validate_file_size(value):
    if value.size > MAX_UPLOAD_SIZE:
        tamanho_mb = value.size / (1024 * 1024)
        raise ValidationError(
            f'O arquivo "{value.name}" tem {tamanho_mb:.1f} MB e excede o limite de '
            f'{MAX_UPLOAD_SIZE // (1024 * 1024)} MB. Reduza o tamanho ou envie outro arquivo.'
        )
