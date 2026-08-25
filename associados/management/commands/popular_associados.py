"""Cria/complementa fichas de Associado a partir dos Atendimentos existentes.

Idempotente: pode ser re-executado com segurança. Requer a FIELD_ENCRYPTION_KEY
do ambiente correto (os CPFs são decifrados registro a registro).

Uso:
    python manage.py popular_associados [--dry-run]
Produção (Railway):
    railway run python manage.py popular_associados
"""
from collections import defaultdict

from django.core.management.base import BaseCommand

from associados.models import Associado, NOME_PLACEHOLDER
from atendimento.models import Atendimento


class Command(BaseCommand):
    help = 'Popula fichas de Associado retroativamente a partir dos Atendimentos.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='Apenas mostra o que seria feito, sem gravar.')

    def handle(self, *args, **options):
        dry = options['dry_run']

        por_hash = defaultdict(list)
        qs = Atendimento.objects.exclude(cpf_hash='').order_by('-created_at')
        for at in qs.iterator():
            por_hash[at.cpf_hash].append(at)

        criados = atualizados = vinculados = 0
        for h, ats in por_hash.items():
            # Mais recente com dados reais (nome não-placeholder e CPF preenchido)
            fonte = next(
                (a for a in ats
                 if a.cpf and (a.nome_filiado or '').strip() not in ('', NOME_PLACEHOLDER)),
                ats[0],
            )
            if dry:
                existe = Associado.objects.filter(cpf_hash=h).exists()
                self.stdout.write(
                    f'[dry-run] {"atualiza" if existe else "cria"} ficha de '
                    f'"{fonte.nome_filiado}" ({len(ats)} atendimento(s))'
                )
                continue

            ja_existia = Associado.objects.filter(cpf_hash=h).exists()
            obj = Associado.upsert_from_atendimento(fonte, Associado.Origem.RETROATIVO)
            if obj is None:
                continue
            if ja_existia:
                atualizados += 1
            else:
                criados += 1
            vinculados += Atendimento.objects.filter(
                cpf_hash=h, associado__isnull=True
            ).update(associado=obj)

        if dry:
            self.stdout.write(self.style.SUCCESS(
                f'[dry-run] {len(por_hash)} CPFs distintos encontrados.'
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f'Fichas criadas: {criados} | complementadas: {atualizados} | '
                f'atendimentos vinculados: {vinculados}'
            ))
