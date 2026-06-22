from datetime import date
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.middleware import AuditMiddleware
from core.models import AuditLog, CustomUser, Notification

from .forms import AtividadeDiretoriaForm, ReembolsoForm
from .models import (
    AtividadeDiretoria,
    PagamentoDiretoria,
    ParametroFinanceiro,
    Reembolso,
    valor_hora_efetivo,
)


# ───────────────────────── Helpers de permissão ─────────────────────────

def _is_financeiro(user):
    return user.is_financeiro


def _is_aprovador_diretoria(user):
    return user.is_aprovador_diretoria or user.is_admin_ti


def _is_gestor_financeiro(user):
    """Dept Financeiro OU aprovador de diretoria (Thabata) — opera o módulo (paga, rejeita)."""
    return _is_financeiro(user) or _is_aprovador_diretoria(user)


def _pode_ver_tudo(user):
    """Quem tem visão completa (leitura) do módulo financeiro: gestores + presidente/coord geral."""
    return _is_gestor_financeiro(user) or user.is_presidente


def _pode_lancar_diretoria(user):
    return user.role == CustomUser.Role.DIRETOR or user.is_admin_ti


def _financeiro_users():
    return CustomUser.objects.filter(
        is_active=True, is_approved=True, departments__slug='financeiro'
    ).distinct()


def _aprovadores_diretoria():
    return CustomUser.objects.filter(
        is_active=True, is_approved=True, is_aprovador_diretoria=True
    )


def _ip(request):
    return AuditMiddleware.get_client_ip(request)


_MESES_PT = ['Janeiro','Fevereiro','Março','Abril','Maio','Junho',
             'Julho','Agosto','Setembro','Outubro','Novembro','Dezembro']


def _ultimos_meses(n=13):
    """Retorna lista de dicts {value, label} dos últimos N meses, do mais recente ao mais antigo."""
    today = date.today()
    meses = []
    y, m = today.year, today.month
    for _ in range(n):
        meses.append({'value': f'{y}-{m:02d}', 'label': f'{_MESES_PT[m-1]} {y}'})
        m -= 1
        if m == 0:
            m, y = 12, y - 1
    return meses


def _parse_competencia(s):
    """Converte 'YYYY-MM' no 1º dia do mês (date) ou None."""
    if not s:
        return None
    try:
        year, month = s.split('-')
        return date(int(year), int(month), 1)
    except (ValueError, TypeError):
        return None


# ───────────────────────── Home ─────────────────────────

@login_required
def home(request):
    user = request.user
    gestor = _is_gestor_financeiro(user)
    aprovador = _is_aprovador_diretoria(user)
    ctx = {
        'is_financeiro': gestor,
        'is_aprovador': aprovador,
        'pode_lancar': _pode_lancar_diretoria(user),
        'meus_reembolsos': Reembolso.objects.filter(solicitante=user)[:5],
    }
    if gestor:
        reemb_pend_qs = Reembolso.objects.filter(status=Reembolso.Status.PENDENTE)
        ctx['reembolsos_pendentes'] = reemb_pend_qs.count()
        ctx['total_reemb_pendente'] = reemb_pend_qs.aggregate(t=Sum('valor'))['t'] or Decimal('0')
        ctx['diretoria_a_pagar'] = AtividadeDiretoria.objects.filter(
            status=AtividadeDiretoria.Status.APROVADA
        ).count()
    if aprovador:
        ctx['atividades_pendentes'] = AtividadeDiretoria.objects.filter(
            status=AtividadeDiretoria.Status.PENDENTE
        ).count()
    if ctx['pode_lancar']:
        ctx['minhas_atividades'] = AtividadeDiretoria.objects.filter(diretor=user)[:5]
    return render(request, 'financeiro/home.html', ctx)


# ───────────────────────── Reembolsos ─────────────────────────

@login_required
def reembolso_list(request):
    user = request.user
    visualiza_tudo = _pode_ver_tudo(user)
    qs = Reembolso.objects.select_related('solicitante')
    if not visualiza_tudo:
        qs = qs.filter(solicitante=user)
    status = request.GET.get('status', '')
    if status:
        qs = qs.filter(status=status)
    total_valor = qs.aggregate(t=Sum('valor'))['t'] or Decimal('0') if visualiza_tudo else None
    return render(request, 'financeiro/reembolso_list.html', {
        'reembolsos': qs,
        'is_financeiro': visualiza_tudo,
        'status_atual': status,
        'status_choices': Reembolso.Status.choices,
        'total_valor': total_valor,
    })


@login_required
def reembolso_create(request):
    if request.method == 'POST':
        form = ReembolsoForm(request.POST, request.FILES)
        if form.is_valid():
            r = form.save(commit=False)
            r.solicitante = request.user
            r.save()
            AuditLog.log(request.user, AuditLog.Action.REEMB_CREATE, 'Reembolso', r.pk, ip=_ip(request))
            link = f'/financeiro/reembolsos/{r.pk}/'
            for fin in _financeiro_users():
                Notification.send(
                    fin, request.user, Notification.Type.REEMBOLSO_NOVO,
                    'Novo reembolso para análise', f'{r.titulo} — R$ {r.valor}', link,
                )
            for ap in _aprovadores_diretoria():
                if not _financeiro_users().filter(pk=ap.pk).exists():
                    Notification.send(
                        ap, request.user, Notification.Type.REEMBOLSO_NOVO,
                        'Novo reembolso para análise', f'{r.titulo} — R$ {r.valor}', link,
                    )
            messages.success(request, 'Reembolso enviado para análise.')
            return redirect('financeiro:reembolso_detail', pk=r.pk)
    else:
        form = ReembolsoForm()
    return render(request, 'financeiro/reembolso_form.html', {'form': form})


@login_required
def reembolso_detail(request, pk):
    r = get_object_or_404(
        Reembolso.objects.select_related('solicitante', 'pago_por'), pk=pk
    )
    user = request.user
    visualiza_tudo = _pode_ver_tudo(user)
    if r.solicitante_id != user.pk and not visualiza_tudo:
        return HttpResponseForbidden()
    return render(request, 'financeiro/reembolso_detail.html', {
        'r': r,
        'is_financeiro': visualiza_tudo,
        'pode_acionar': _is_gestor_financeiro(user),
    })


@login_required
@require_POST
def reembolso_pagar(request, pk):
    r = get_object_or_404(Reembolso, pk=pk)
    if not _is_gestor_financeiro(request.user):
        return HttpResponseForbidden()
    if r.status != Reembolso.Status.PENDENTE:
        messages.error(request, 'Este reembolso não está aguardando pagamento.')
        return redirect('financeiro:reembolso_detail', pk=pk)
    r.status = Reembolso.Status.PAGO
    r.pago_por = request.user
    r.pago_em = timezone.now()
    r.save()
    AuditLog.log(request.user, AuditLog.Action.REEMB_PAY, 'Reembolso', r.pk, ip=_ip(request))
    Notification.send(
        r.solicitante, request.user, Notification.Type.REEMBOLSO_STATUS,
        'Reembolso pago', r.titulo, f'/financeiro/reembolsos/{r.pk}/',
    )
    messages.success(request, 'Pagamento do reembolso confirmado.')
    return redirect(request.POST.get('next') or f'/financeiro/reembolsos/{r.pk}/')


@login_required
@require_POST
def reembolso_rejeitar(request, pk):
    r = get_object_or_404(Reembolso, pk=pk)
    if not _is_gestor_financeiro(request.user):
        return HttpResponseForbidden()
    if r.status != Reembolso.Status.PENDENTE:
        messages.error(request, 'Este reembolso não pode ser rejeitado.')
        return redirect('financeiro:reembolso_detail', pk=pk)
    motivo = (request.POST.get('motivo') or '').strip()
    r.status = Reembolso.Status.REJEITADO
    r.motivo_rejeicao = motivo
    r.save()
    AuditLog.log(request.user, AuditLog.Action.REEMB_REJECT, 'Reembolso', r.pk, ip=_ip(request))
    Notification.send(
        r.solicitante, request.user, Notification.Type.REEMBOLSO_STATUS,
        'Reembolso rejeitado', motivo or r.titulo, f'/financeiro/reembolsos/{r.pk}/',
    )
    messages.success(request, 'Reembolso rejeitado.')
    return redirect('financeiro:reembolso_detail', pk=pk)


# ───────────────────────── Atividades de diretoria ─────────────────────────

@login_required
def atividade_list(request):
    user = request.user
    pode_lancar = _pode_lancar_diretoria(user)
    is_aprovador = _is_aprovador_diretoria(user)
    visualiza_tudo = _pode_ver_tudo(user)

    aba = request.GET.get('aba')
    if aba is None:
        aba = 'aprovar' if (visualiza_tudo and not pode_lancar) else 'minhas'
    if aba == 'aprovar' and visualiza_tudo:
        atividades = AtividadeDiretoria.objects.select_related('diretor').filter(
            status=AtividadeDiretoria.Status.PENDENTE
        )
    else:
        aba = 'minhas'
        atividades = AtividadeDiretoria.objects.select_related('diretor').filter(diretor=user)

    params = ParametroFinanceiro.get()
    atividades_list = list(atividades)
    for a in atividades_list:
        vh = a.diretor.valor_hora_diretoria or params.valor_hora_diretoria_padrao
        a.valor_estimado = a.horas_efetivas * vh

    return render(request, 'financeiro/atividade_list.html', {
        'atividades': atividades_list,
        'pode_lancar': pode_lancar,
        'is_aprovador': is_aprovador,
        'is_financeiro': visualiza_tudo,
        'visualiza_tudo': visualiza_tudo,
        'aba': aba,
    })


@login_required
def atividade_create(request):
    if not _pode_lancar_diretoria(request.user):
        return HttpResponseForbidden()
    if request.method == 'POST':
        form = AtividadeDiretoriaForm(request.POST, request.FILES)
        if form.is_valid():
            a = form.save(commit=False)
            a.diretor = request.user
            a.save()
            AuditLog.log(request.user, AuditLog.Action.DIRAT_CREATE, 'AtividadeDiretoria', a.pk, ip=_ip(request))
            link = f'/financeiro/diretoria/{a.pk}/'
            for ap in _aprovadores_diretoria():
                Notification.send(
                    ap, request.user, Notification.Type.DIRETORIA_NOVA,
                    'Nova atividade para aprovar', f'{a.titulo} — {a.horas}h', link,
                )
            messages.success(request, 'Atividade registrada e enviada para aprovação.')
            return redirect('financeiro:atividade_detail', pk=a.pk)
    else:
        form = AtividadeDiretoriaForm()

    hoje = timezone.localdate()
    comp = hoje.replace(day=1)
    teto = ParametroFinanceiro.get().teto_horas_mensal
    horas_mes = AtividadeDiretoria.objects.filter(
        diretor=request.user, competencia=comp,
    ).exclude(status=AtividadeDiretoria.Status.REJEITADA).aggregate(
        total=Sum('horas')
    )['total'] or Decimal('0')

    return render(request, 'financeiro/atividade_form.html', {
        'form': form, 'teto': teto, 'horas_mes': horas_mes, 'competencia': comp,
    })


@login_required
def atividade_detail(request, pk):
    a = get_object_or_404(
        AtividadeDiretoria.objects.select_related('diretor', 'aprovado_por', 'pagamento'), pk=pk
    )
    user = request.user
    if a.diretor_id != user.pk and not _pode_ver_tudo(user):
        return HttpResponseForbidden()
    horas_mes_diretor = AtividadeDiretoria.objects.filter(
        diretor=a.diretor, competencia=a.competencia,
    ).exclude(status=AtividadeDiretoria.Status.REJEITADA).aggregate(
        total=Sum('horas')
    )['total'] or Decimal('0')
    teto_mensal = ParametroFinanceiro.get().teto_horas_mensal
    return render(request, 'financeiro/atividade_detail.html', {
        'a': a,
        'is_aprovador': _is_aprovador_diretoria(user),
        'horas_mes_diretor': horas_mes_diretor,
        'teto_mensal': teto_mensal,
    })


@login_required
@require_POST
def atividade_aprovar(request, pk):
    a = get_object_or_404(AtividadeDiretoria, pk=pk)
    if not _is_aprovador_diretoria(request.user):
        return HttpResponseForbidden()
    if a.status != AtividadeDiretoria.Status.PENDENTE:
        messages.error(request, 'Esta atividade não está pendente.')
        return redirect('financeiro:atividade_detail', pk=pk)

    # Horas aprovadas: por padrão = horas lançadas; aprovação parcial usa um valor menor.
    raw = (request.POST.get('horas_aprovadas') or '').strip().replace(',', '.')
    horas_aprovadas = a.horas
    if raw:
        try:
            horas_aprovadas = Decimal(raw)
        except InvalidOperation:
            messages.error(request, 'Horas a aprovar inválidas.')
            return redirect('financeiro:atividade_detail', pk=pk)
        if horas_aprovadas <= 0 or horas_aprovadas > a.horas:
            messages.error(request, f'As horas aprovadas devem ser maiores que 0 e no máximo {a.horas}h (lançadas).')
            return redirect('financeiro:atividade_detail', pk=pk)

    a.status = AtividadeDiretoria.Status.APROVADA
    a.horas_aprovadas = horas_aprovadas
    a.aprovado_por = request.user
    a.aprovado_em = timezone.now()
    a.save()
    AuditLog.log(
        request.user, AuditLog.Action.DIRAT_APPROVE, 'AtividadeDiretoria', a.pk, ip=_ip(request),
        horas_lancadas=str(a.horas), horas_aprovadas=str(horas_aprovadas),
    )
    parcial = horas_aprovadas < a.horas
    if parcial:
        titulo_notif = 'Atividade aprovada parcialmente'
        corpo_notif = f'{a.titulo} — {horas_aprovadas}h aprovadas de {a.horas}h lançadas'
        msg = f'Atividade aprovada parcialmente: {horas_aprovadas}h de {a.horas}h.'
    else:
        titulo_notif = 'Atividade aprovada'
        corpo_notif = a.titulo
        msg = 'Atividade aprovada.'
    Notification.send(
        a.diretor, request.user, Notification.Type.DIRETORIA_STATUS,
        titulo_notif, corpo_notif, f'/financeiro/diretoria/{a.pk}/',
    )
    messages.success(request, msg)
    return redirect(request.POST.get('next') or f'/financeiro/diretoria/{a.pk}/')


@login_required
@require_POST
def atividade_rejeitar(request, pk):
    a = get_object_or_404(AtividadeDiretoria, pk=pk)
    if not _is_aprovador_diretoria(request.user):
        return HttpResponseForbidden()
    if a.status != AtividadeDiretoria.Status.PENDENTE:
        messages.error(request, 'Esta atividade não está pendente.')
        return redirect('financeiro:atividade_detail', pk=pk)
    motivo = (request.POST.get('motivo') or '').strip()
    a.status = AtividadeDiretoria.Status.REJEITADA
    a.motivo_rejeicao = motivo
    a.save()
    AuditLog.log(request.user, AuditLog.Action.DIRAT_REJECT, 'AtividadeDiretoria', a.pk, ip=_ip(request))
    Notification.send(
        a.diretor, request.user, Notification.Type.DIRETORIA_STATUS,
        'Atividade rejeitada', motivo or a.titulo, f'/financeiro/diretoria/{a.pk}/',
    )
    messages.success(request, 'Atividade rejeitada.')
    return redirect(request.POST.get('next') or f'/financeiro/diretoria/{a.pk}/')


# ───────────────────────── Pagamentos (a pagar + realizados) ─────────────────────────

@login_required
def pagamentos(request):
    user = request.user
    if not _pode_ver_tudo(user):
        return HttpResponseForbidden()
    pode_acionar = _is_gestor_financeiro(user)

    teto = ParametroFinanceiro.get().teto_horas_mensal
    comp_str = request.GET.get('competencia', '')
    comp_filter = _parse_competencia(comp_str)

    # ── A pagar ──
    reembolsos = Reembolso.objects.select_related('solicitante').filter(
        status=Reembolso.Status.PENDENTE
    )

    aprovadas = AtividadeDiretoria.objects.select_related('diretor').filter(
        status=AtividadeDiretoria.Status.APROVADA
    )
    if comp_filter:
        aprovadas = aprovadas.filter(competencia=comp_filter)

    grupos_map = {}
    for ativ in aprovadas:
        grupos_map.setdefault((ativ.diretor_id, ativ.competencia), []).append(ativ)

    grupos = []
    for (diretor_id, competencia), itens in grupos_map.items():
        diretor = itens[0].diretor
        horas_totais = sum((i.horas_efetivas for i in itens), Decimal('0'))
        horas_pagas = min(horas_totais, teto)
        vh = valor_hora_efetivo(diretor)
        grupos.append({
            'diretor': diretor,
            'competencia': competencia,
            'competencia_str': competencia.strftime('%Y-%m'),
            'qtd': len(itens),
            'horas_totais': horas_totais,
            'horas_pagas': horas_pagas,
            'valor_hora': vh,
            'valor_total': horas_pagas * vh,
            'excedeu': horas_totais > teto,
        })
    grupos.sort(key=lambda g: (g['competencia'], g['diretor'].get_full_name() or ''), reverse=True)

    # ── Pagamentos realizados ──
    pagamentos_dir = PagamentoDiretoria.objects.select_related('diretor', 'pago_por')
    reembolsos_pagos = Reembolso.objects.select_related('solicitante', 'pago_por').filter(
        status=Reembolso.Status.PAGO
    ).order_by('-pago_em')
    if comp_filter:
        pagamentos_dir = pagamentos_dir.filter(competencia=comp_filter)
        reembolsos_pagos = reembolsos_pagos.filter(
            pago_em__year=comp_filter.year,
            pago_em__month=comp_filter.month,
        )

    # ── Totais para os cards de resumo ──
    total_reemb_pendente = reembolsos.aggregate(t=Sum('valor'))['t'] or Decimal('0')
    total_dir_pendente = sum(g['valor_total'] for g in grupos)
    total_reemb_pago = reembolsos_pagos.aggregate(t=Sum('valor'))['t'] or Decimal('0')
    total_dir_pago = pagamentos_dir.aggregate(t=Sum('valor_total'))['t'] or Decimal('0')

    return render(request, 'financeiro/pagamentos.html', {
        'pode_acionar': pode_acionar,
        # a pagar
        'reembolsos': reembolsos,
        'grupos': grupos,
        'teto': teto,
        # realizados
        'pagamentos_dir': pagamentos_dir,
        'reembolsos_pagos': reembolsos_pagos,
        # totais
        'total_reemb_pendente': total_reemb_pendente,
        'total_dir_pendente': total_dir_pendente,
        'total_reemb_pago': total_reemb_pago,
        'total_dir_pago': total_dir_pago,
        # filtro
        'competencia_filtro': comp_str,
        'meses_disponiveis': _ultimos_meses(),
    })


@login_required
@require_POST
def diretoria_pagar(request):
    user = request.user
    if not _is_gestor_financeiro(user):
        return HttpResponseForbidden()

    diretor_id = request.POST.get('diretor')
    competencia = _parse_competencia(request.POST.get('competencia'))
    if not diretor_id or not competencia:
        messages.error(request, 'Dados inválidos para o pagamento.')
        return redirect('financeiro:pagamentos')

    diretor = get_object_or_404(CustomUser, pk=diretor_id)
    itens = list(AtividadeDiretoria.objects.filter(
        diretor=diretor, competencia=competencia, status=AtividadeDiretoria.Status.APROVADA
    ))
    if not itens:
        messages.error(request, 'Não há atividades aprovadas para pagar nesta competência.')
        return redirect('financeiro:pagamentos')

    teto = ParametroFinanceiro.get().teto_horas_mensal
    horas_totais = sum((i.horas_efetivas for i in itens), Decimal('0'))
    horas_pagas = min(horas_totais, teto)
    vh = valor_hora_efetivo(diretor)

    pagamento, created = PagamentoDiretoria.objects.get_or_create(
        diretor=diretor, competencia=competencia,
        defaults={
            'horas_totais': horas_totais,
            'horas_pagas': horas_pagas,
            'valor_hora': vh,
            'valor_total': horas_pagas * vh,
            'pago_por': user,
            'pago_em': timezone.now(),
        },
    )
    if not created:
        messages.info(request, 'Esta competência já foi paga para este diretor.')
        return redirect('financeiro:pagamentos')

    for i in itens:
        i.status = AtividadeDiretoria.Status.PAGA
        i.pagamento = pagamento
        i.save()

    AuditLog.log(user, AuditLog.Action.DIRAT_PAY, 'PagamentoDiretoria', pagamento.pk, ip=_ip(request))
    Notification.send(
        diretor, user, Notification.Type.DIRETORIA_PAGO,
        'Pagamento de diretoria realizado',
        f'Competência {competencia:%m/%Y}: {pagamento.horas_pagas}h — R$ {pagamento.valor_total}',
        '/financeiro/diretoria/',
    )
    messages.success(
        request,
        f'Pagamento de {diretor.get_full_name() or diretor} ({competencia:%m/%Y}) confirmado.',
    )
    return redirect('financeiro:pagamentos')


# ───────────────────────── Configuração de diretores ─────────────────────────

@login_required
def diretor_config(request):
    """Configura valor/hora individual por diretor e parâmetros globais. Acesso: financeiro + Thabata."""
    if not _is_gestor_financeiro(request.user):
        return HttpResponseForbidden()

    params = ParametroFinanceiro.get()
    diretores = CustomUser.objects.filter(
        role=CustomUser.Role.DIRETOR, is_active=True, is_approved=True
    ).order_by('first_name', 'last_name')

    if request.method == 'POST':
        erros = []

        # Parâmetros globais
        try:
            params.valor_hora_diretoria_padrao = Decimal(
                request.POST.get('valor_hora_padrao', '').replace(',', '.') or '0'
            )
            params.teto_horas_mensal = Decimal(
                request.POST.get('teto_horas_mensal', '').replace(',', '.') or '0'
            )
            params.save()
        except InvalidOperation:
            erros.append('Valores dos parâmetros globais inválidos.')

        # Override por diretor
        for d in diretores:
            raw = request.POST.get(f'vh_{d.pk}', '').strip().replace(',', '.')
            try:
                d.valor_hora_diretoria = Decimal(raw) if raw else None
                d.save(update_fields=['valor_hora_diretoria'])
            except InvalidOperation:
                erros.append(f'Valor inválido para {d.get_full_name() or d.email}.')

        if erros:
            for e in erros:
                messages.error(request, e)
        else:
            messages.success(request, 'Configurações salvas com sucesso.')
        return redirect('financeiro:diretor_config')

    return render(request, 'financeiro/diretor_config.html', {
        'params': params,
        'diretores': diretores,
    })
