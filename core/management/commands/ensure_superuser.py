from django.core.management.base import BaseCommand
from decouple import config


class Command(BaseCommand):
    help = 'Cria ou atualiza superusuário a partir de variáveis de ambiente'

    def handle(self, *args, **options):
        from core.models import CustomUser
        email = config('DJANGO_SUPERUSER_EMAIL', default='')
        password = config('DJANGO_SUPERUSER_PASSWORD', default='')

        self.stdout.write(f'[ensure_superuser] email={email!r} password_set={bool(password)}')

        if not email or not password:
            self.stdout.write(self.style.WARNING(
                '[ensure_superuser] DJANGO_SUPERUSER_EMAIL ou DJANGO_SUPERUSER_PASSWORD não definidos, pulando.'
            ))
            return

        user, created = CustomUser.objects.get_or_create(
            email__iexact=email,
            defaults={'username': CustomUser.generate_username(email), 'email': email},
        )

        user.set_password(password)
        user.is_active = True
        user.is_staff = True
        user.is_superuser = True
        user.is_approved = True
        user.lgpd_consent = True
        user.role = CustomUser.Role.ADMIN_TI
        user.save()

        if created:
            self.stdout.write(self.style.SUCCESS(f'[ensure_superuser] Superusuário {email} criado com sucesso.'))
        else:
            self.stdout.write(self.style.SUCCESS(f'[ensure_superuser] Superusuário {email} atualizado (senha redefinida).'))
