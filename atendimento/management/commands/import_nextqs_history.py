import re
from datetime import datetime, timezone, timedelta

import requests
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.models.functions import TruncDate
from django.utils.timezone import now

from atendimento.models import Atendimento, AtendimentoEtapa, _cpf_hash
from core.models import Department

_FILA_PARA_DEPT = {
    'P': 'Jurídico',
    'T': 'Jurídico',
    'A': 'Jurídico',
    'M': 'Saúde do Trabalhador',
    'D': 'Ouvidoria',
}

_VALID_FILAS = {'P', 'T', 'A', 'M', 'D'}


def _parse_dt(s):
    if not s:
        return None
    for fmt in ('%Y-%m-%dT%H:%M:%S.%fZ', '%Y-%m-%dT%H:%M:%SZ', '%Y-%m-%dT%H:%M:%S'):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _extract_field(support_fields, label):
    for f in (support_fields or []):
        if f.get('label', '').strip().lower() == label.lower():
            return (f.get('value') or '').strip()
    return ''


def _clean_cpf(raw):
    digits = re.sub(r'\D', '', raw or '')
    if len(digits) != 11 or len(set(digits)) == 1:
        return ''
    return f'{digits[:3]}.{digits[3:6]}.{digits[6:9]}-{digits[9:]}'


class Command(BaseCommand):
    help = 'Importa atendimentos históricos do NextQS para o sistema'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days', type=int, default=7,
            help='Quantos dias atrás importar (padrão: 7)',
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Lista o que seria importado sem gravar no banco',
        )

    def handle(self, *args, **options):
        api_key = getattr(settings, 'NEXTQS_API_KEY', '')
        api_base = getattr(settings, 'NEXTQS_API_BASE', 'https://api.nextqs.com')
        if not api_key:
            self.stderr.write(self.style.ERROR('NEXTQS_API_KEY não configurado.'))
            return

        days = options['days']
        dry_run = options['dry_run']
        cutoff = now() - timedelta(days=days)

        if dry_run:
            self.stdout.write(self.style.WARNING('[DRY-RUN] Nenhum dado será gravado.'))

        self.stdout.write(
            f'Buscando registros dos últimos {days} dias '
            f'(desde {cutoff.strftime("%d/%m/%Y %H:%M")})...'
        )

        try:
            r = requests.get(
                f'{api_base}/v1/organization/reports',
                headers={'Authorization': f'Bearer {api_key}'},
                timeout=30,
            )
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            self.stderr.write(self.style.ERROR(f'Erro ao buscar NextQS: {e}'))
            return

        records = data if isinstance(data, list) else data.get('data', data.get('items', []))
        self.stdout.write(f'Total de registros na API: {len(records)}')

        filtered = []
        for rec in records:
            dt = _parse_dt(rec.get('ticket_generated_at'))
            if dt and dt >= cutoff:
                rec['_generated_at'] = dt
                filtered.append(rec)

        self.stdout.write(f'Registros no período: {len(filtered)}')
        if not filtered:
            self.stdout.write('Nenhum registro para importar.')
            return

        # (fila, numero, date) de tudo que já está no banco com nextqs_fila preenchido
        existing_keys = set(
            Atendimento.objects.filter(nextqs_fila__in=_VALID_FILAS)
            .exclude(numero_senha='')
            .annotate(date_only=TruncDate('created_at'))
            .values_list('nextqs_fila', 'numero_senha', 'date_only')
        )

        dept_cache = {}

        def get_dept(nome):
            if nome not in dept_cache:
                try:
                    dept_cache[nome] = Department.objects.get(name=nome)
                except Department.DoesNotExist:
                    dept_cache[nome] = None
                    self.stderr.write(self.style.WARNING(f'Departamento não encontrado: {nome}'))
            return dept_cache[nome]

        importados = 0
        ignorados = 0

        for rec in filtered:
            alpha = (rec.get('ticket_alpha') or '').strip()
            numero = str(rec.get('ticket_number') or '').strip()
            generated_at = rec['_generated_at']

            if not alpha or not numero or alpha not in _VALID_FILAS:
                ignorados += 1
                continue

            date_key = generated_at.date()
            if (alpha, numero, date_key) in existing_keys:
                ignorados += 1
                continue

            support_fields = rec.get('support_fields', [])
            nome_raw = _extract_field(support_fields, 'Nome') or 'Aguardando identificação'
            cpf_raw = _extract_field(support_fields, 'CPF')
            assunto_raw = _extract_field(support_fields, 'Cargo') or f'Fila {alpha}'

            cpf_clean = _clean_cpf(cpf_raw)

            started_at = _parse_dt(rec.get('service_started_at'))
            ended_at = _parse_dt(rec.get('service_ended_at'))
            is_noshow = bool(rec.get('is_noshow'))

            if is_noshow:
                status = Atendimento.Status.CANCELADO
            elif ended_at:
                status = Atendimento.Status.CONCLUIDO
            else:
                status = Atendimento.Status.TRIAGEM

            if dry_run:
                self.stdout.write(
                    f'  {alpha}{numero} | {nome_raw[:30]:<30} | {assunto_raw[:20]:<20} '
                    f'| {status:<12} | {generated_at.strftime("%d/%m/%Y %H:%M")}'
                )
                importados += 1
                existing_keys.add((alpha, numero, date_key))
                continue

            at = Atendimento(
                cpf=cpf_clean,
                nome_filiado=nome_raw[:200],
                assunto=assunto_raw[:200],
                nextqs_fila=alpha,
                numero_senha=numero,
                is_auto_nextqs=True,
                status=status,
                criado_por=None,
                iniciado_em=started_at,
                concluido_em=ended_at,
            )
            at.save()

            # Retrodate created_at to actual ticket generation time
            Atendimento.objects.filter(pk=at.pk).update(created_at=generated_at)
            at.created_at = generated_at

            AtendimentoEtapa.objects.create(
                atendimento=at,
                tipo=AtendimentoEtapa.Tipo.ABERTURA,
                autor=None,
                departamento=None,
                descricao=(
                    f'Importado automaticamente do NextQS. '
                    f'Senha {alpha}{numero} gerada em {generated_at.strftime("%d/%m/%Y %H:%M")}.'
                ),
                created_at=generated_at,
            )

            # Route to department (silent, no notifications)
            nome_dept = _FILA_PARA_DEPT.get(alpha)
            dept = get_dept(nome_dept) if nome_dept else None
            if dept and status != Atendimento.Status.CANCELADO:
                AtendimentoEtapa.objects.create(
                    atendimento=at,
                    tipo=AtendimentoEtapa.Tipo.ENCAMINHAMENTO,
                    autor=None,
                    departamento=None,
                    para_departamento=dept,
                    descricao=f'Encaminhado automaticamente para {dept.name} (importado do NextQS).',
                    created_at=generated_at,
                )
                at.departamento_atual = dept
                if status == Atendimento.Status.TRIAGEM:
                    at.status = Atendimento.Status.ENCAMINHADO
                    status = at.status
                at.save(update_fields=['departamento_atual', 'status', 'updated_at'])

            if is_noshow:
                AtendimentoEtapa.objects.create(
                    atendimento=at,
                    tipo=AtendimentoEtapa.Tipo.CANCELAMENTO,
                    autor=None,
                    departamento=dept,
                    descricao='Não compareceu (no-show). Cancelado automaticamente.',
                    created_at=ended_at or generated_at,
                )
            elif ended_at:
                AtendimentoEtapa.objects.create(
                    atendimento=at,
                    tipo=AtendimentoEtapa.Tipo.CONCLUSAO,
                    autor=None,
                    departamento=dept,
                    descricao='Atendimento concluído. (Importado do NextQS.)',
                    created_at=ended_at,
                )

            existing_keys.add((alpha, numero, date_key))
            importados += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'\nConcluído: {importados} importados, '
                f'{ignorados} ignorados (já existentes ou inválidos).'
            )
        )
