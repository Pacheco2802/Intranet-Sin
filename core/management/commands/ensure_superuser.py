from django.core.management.base import BaseCommand
from decouple import config


class Command(BaseCommand):
    help = 'Cria ou atualiza superusuário a partir de variáveis de ambiente'

    def handle(self, *args, **options):
        from core.models import CustomUser

        email = config('DJANGO_SUPERUSER_EMAIL', default='')
        password = config('DJANGO_SUPERUSER_PASSWORD', default='')

        print(f'[ensure_superuser] iniciando — email={email!r} senha_definida={bool(password)}', flush=True)

        if not email or not password:
            print('[ensure_superuser] variáveis não definidas, pulando.', flush=True)
            return

        try:
            user = CustomUser.objects.get(email__iexact=email)
            user.set_password(password)
            user.is_active = True
            user.is_staff = True
            user.is_superuser = True
            user.is_approved = True
            user.lgpd_consent = True
            user.role = CustomUser.Role.ADMIN_TI
            user.save()
            print(f'[ensure_superuser] usuário {email} já existia — senha e permissões atualizadas.', flush=True)
        except CustomUser.DoesNotExist:
            user = CustomUser(
                username=CustomUser.generate_username(email),
                email=email,
                is_active=True,
                is_staff=True,
                is_superuser=True,
                is_approved=True,
                lgpd_consent=True,
                role=CustomUser.Role.ADMIN_TI,
            )
            user.set_password(password)
            user.save()
            print(f'[ensure_superuser] superusuário {email} criado com sucesso.', flush=True)
