"""
Varredura de diagnóstico: por que uma atendente fica sem o botão de imprimir senha?
Read-only. Rodar contra PRODUÇÃO:

    railway run python varredura_senhas.py        # com Railway CLI linkado
    # ou, com a URL pública do Postgres exportada:
    DATABASE_URL="<DATABASE_PUBLIC_URL>" python varredura_senhas.py

O botão "Imprimir senha" só aparece quando nextqs_fila E numero_senha estão preenchidos.
Se os atendimentos de UMA atendente vierem com numero_senha vazio -> emissão NextQS falhou (sistema).
Se vierem preenchidos -> emissão OK, é operacional (onde ela olha/clica).
"""
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "intranet.settings")
django.setup()

from datetime import timedelta
from django.utils.timezone import now
from django.db.models import Count, Q
from atendimento.models import Atendimento

desde = now() - timedelta(days=30)
qs = Atendimento.objects.filter(created_at__gte=desde)

print(f"Total de atendimentos nos ultimos 30 dias: {qs.count()}\n")
print("=== Por atendente (quem criou) ===")
print(f"{'atendente':<22}{'total':>6}{'c/fila':>8}{'c/senha':>9}{'SEM senha (c/fila)':>20}")
rows = (
    qs.values("criado_por__username", "criado_por__first_name")
    .annotate(
        total=Count("id"),
        com_fila=Count("id", filter=~Q(nextqs_fila="")),
        com_senha=Count("id", filter=~Q(numero_senha="")),
        sem_senha_com_fila=Count("id", filter=Q(numero_senha="") & ~Q(nextqs_fila="")),
    )
    .order_by("-total")
)
for r in rows:
    nome = r["criado_por__first_name"] or r["criado_por__username"] or "(sistema/auto)"
    print(f"{nome:<22}{r['total']:>6}{r['com_fila']:>8}{r['com_senha']:>9}{r['sem_senha_com_fila']:>20}")

print("\n=== Atendimentos c/ fila mas SEM numero_senha (emissao falhou) — ult. 30d ===")
falhas = (
    qs.filter(numero_senha="").exclude(nextqs_fila="")
    .select_related("criado_por")
    .order_by("-created_at")[:20]
)
if not falhas:
    print("Nenhum. Todas as senhas com fila foram emitidas com numero -> nao e falha de emissao.")
for at in falhas:
    quem = (at.criado_por.first_name or at.criado_por.username) if at.criado_por else "auto"
    print(f"  #{at.pk}  {at.created_at:%d/%m %H:%M}  fila={at.nextqs_fila}  por={quem}  status={at.status}  nome={at.nome_filiado[:25]}")
