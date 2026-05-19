from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from core.models import AuditLog, LGPDConsent


class Command(BaseCommand):
    help = 'Remove logs de auditoria com mais de 2 anos e consentimentos LGPD com mais de 5 anos (política de retenção)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Apenas mostra o que seria excluído, sem apagar.',
        )

    def handle(self, *args, **options):
        dry = options['dry_run']
        now = timezone.now()

        audit_cutoff = now - timedelta(days=730)   # 2 anos
        consent_cutoff = now - timedelta(days=1825) # 5 anos

        old_logs = AuditLog.objects.filter(timestamp__lt=audit_cutoff)
        old_consents = LGPDConsent.objects.filter(consent_date__lt=consent_cutoff)

        self.stdout.write(f'Logs de auditoria anteriores a {audit_cutoff.date()}: {old_logs.count()}')
        self.stdout.write(f'Consentimentos LGPD anteriores a {consent_cutoff.date()}: {old_consents.count()}')

        if not dry:
            deleted_logs, _ = old_logs.delete()
            deleted_consents, _ = old_consents.delete()
            self.stdout.write(self.style.SUCCESS(
                f'Excluídos: {deleted_logs} log(s) de auditoria, {deleted_consents} consentimento(s).'
            ))
        else:
            self.stdout.write(self.style.WARNING('Modo dry-run: nenhum dado foi excluído.'))
