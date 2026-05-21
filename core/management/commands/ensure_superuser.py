from django.core.management.base import BaseCommand
from decouple import config


class Command(BaseCommand):
    help = 'Cria superusuário a partir de variáveis de ambiente se não existir'

    def handle(self, *args, **options):
        from core.models import CustomUser
        email = config('DJANGO_SUPERUSER_EMAIL', default='')
        password = config('DJANGO_SUPERUSER_PASSWORD', default='')
        if not email or not password:
            self.stdout.write('DJANGO_SUPERUSER_EMAIL ou DJANGO_SUPERUSER_PASSWORD não definidos, pulando.')
            return
        if CustomUser.objects.filter(email=email).exists():
            self.stdout.write(f'Superusuário {email} já existe.')
            return
        user = CustomUser.objects.create_superuser(
            username=CustomUser.generate_username(email),
            email=email,
            password=password,
        )
        user.role = CustomUser.Role.ADMIN_TI
        user.is_approved = True
        user.lgpd_consent = True
        user.save()
        self.stdout.write(self.style.SUCCESS(f'Superusuário {email} criado com sucesso.'))
