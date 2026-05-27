import json
from collections import defaultdict
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils.timezone import now, localdate

from core.models import AuditLog, Notification, CustomUser, Department
from core.middleware import AuditMiddleware
from core.validators import validate_file_extension, validate_file_size
from .models import Atendimento, AtendimentoEtapa, AtendimentoAnexo, _cpf_hash
from .forms import (
    AtendimentoForm, EtapaNotaForm, EncaminharForm,
    ConcluirForm, AtendimentoFilterForm,
)


def _qs_visivel(user):
    qs = Atendimento.objects.select_related(
        'criado_por', 'departamento_atual', 'responsavel'
    )
    if user.can_see_all:
        return qs
    return qs.filter(
        Q(criado_por=user) |
        Q(departamento_atual__in=user.departments.all()) |
        Q(departamento_atual__leaders=user)
    ).distinct()


def _pode_agir(atendimento, user):
    if user.can_see_all:
        return True
    if atendimento.criado_por == user:
        return True
    if atendimento.departamento_atual_id and user.departments.filter(pk=atendimento.departamento_atual_id).exists():
        return True
    if atendimento.departamento_atual and atendimento.departamento_atual.leaders.filter(pk=user.pk).exists():
        return True
    return False


def _salvar_anexo(arquivo, atendimento, etapa, user):
    if not arquivo:
        return None
    validate_file_extension(arquivo)
    validate_file_size(arquivo)
    return AtendimentoAnexo.objects.create(
        atendimento=atendimento,
        etapa=etapa,
        arquivo=arquivo,
        nome_original=arquivo.name,
        enviado_por=user,
    )


def _notificar_encaminhamento(atendimento, para_dept, actor):
    link = f'/atendimento/{atendimento.pk}/'
    targets = set()
    for ldr in para_dept.leaders.all():
        if ldr != actor:
            targets.add(ldr)
    for member in CustomUser.objects.filter(
        departments=para_dept, is_active=True, is_approved=True
    ):
        if member != actor:
            targets.add(member)
    for user in targets:
        Notification.send(
            user=user, actor=actor,
            ntype=Notification.Type.CARD_CROSS,
            title=f'Atendimento encaminhado para {para_dept.name}',
            body=f'{atendimento.nome_filiado} — {atendimento.assunto}',
            link=link,
        )


# Mapeamento fila NextQS → nome do departamento destino
_FILA_PARA_DEPT = {
    'J': 'Jurídico',
    'P': 'Jurídico',
    'T': 'Jurídico',
    'A': 'Jurídico',
    'M': 'Saúde do Trabalhador',
}


def _encaminhar_automatico(at, criador):
    """Encaminha automaticamente o atendimento para o departamento correto conforme a fila."""
    if not at.nextqs_fila:
        return
    nome_dept = _FILA_PARA_DEPT.get(at.nextqs_fila)
    if not nome_dept:
        return
    # Não encaminha se já está no departamento correto
    if at.departamento_atual and at.departamento_atual.name == nome_dept:
        return
    try:
        dept = Department.objects.get(name=nome_dept)
    except Department.DoesNotExist:
        return
    AtendimentoEtapa.objects.create(
        atendimento=at,
        tipo=AtendimentoEtapa.Tipo.ENCAMINHAMENTO,
        autor=criador,
        departamento=at.departamento_atual,
        para_departamento=dept,
        descricao=f'Encaminhado automaticamente para {dept.name}.',
    )
    at.departamento_atual = dept
    at.status = Atendimento.Status.ENCAMINHADO
    at.save(update_fields=['departamento_atual', 'status', 'updated_at'])
    _notificar_encaminhamento(at, dept, criador)


def _fmt_min(minutes):
    if minutes is None:
        return '—'
    if minutes < 60:
        return f'{minutes}min'
    h = minutes // 60
    m = minutes % 60
    return f'{h}h {m}min' if m else f'{h}h'


@login_required
def atendimento_list(request):
    qs = _qs_visivel(request.user).order_by('-updated_at')
    form = AtendimentoFilterForm(request.GET or None)
    cpf_filtro = ''

    if form.is_valid():
        cpf = form.cleaned_data.get('cpf', '').strip()
        nome = form.cleaned_data.get('nome', '').strip()
        status = form.cleaned_data.get('status', '')
        departamento = form.cleaned_data.get('departamento')

        if cpf:
            cpf_filtro = cpf
            h = _cpf_hash(cpf)
            if h:
                qs = qs.filter(cpf_hash=h)
        if nome:
            qs = qs.filter(nome_filiado__icontains=nome)
        if status:
            qs = qs.filter(status=status)
        if departamento:
            qs = qs.filter(departamento_atual=departamento)

    total = qs.count()
    paginator = Paginator(qs, 25)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    params = request.GET.copy()
    params.pop('page', None)
    base_query = params.urlencode()

    return render(request, 'atendimento/list.html', {
        'atendimentos': page_obj,
        'page_obj': page_obj,
        'form': form,
        'cpf_filtro': cpf_filtro,
        'total': total,
        'base_query': base_query,
    })


@login_required
def atendimento_cpf_lookup(request):
    cpf_raw = request.GET.get('cpf', '')
    h = _cpf_hash(cpf_raw)
    if not h:
        return JsonResponse({'found': False})
    qs = Atendimento.objects.filter(cpf_hash=h).order_by('-created_at')
    first = qs.first()
    if not first:
        return JsonResponse({'found': False})
    anteriores = list(qs.values('pk', 'assunto', 'created_at', 'status'))
    for a in anteriores:
        a['created_at'] = a['created_at'].strftime('%d/%m/%Y')
    return JsonResponse({
        'found': True,
        'nome': first.nome_filiado,
        'telefone': first.telefone or '',
        'email': first.email_filiado or '',
        'total': qs.count(),
        'ultimo_pk': first.pk,
        'cpf_hash': h,
        'anteriores': anteriores[:10],
    })


@login_required
def atendimento_create(request):
    form = AtendimentoForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        at = form.save(commit=False)
        at.criado_por = request.user
        at.departamento_atual = request.user.department
        h = _cpf_hash(at.cpf)
        retorno_pk = request.POST.get('retorno_de')
        if at.is_retorno and retorno_pk:
            try:
                at.retorno_de = Atendimento.objects.get(pk=retorno_pk, cpf_hash=h)
            except Atendimento.DoesNotExist:
                at.retorno_de = None
        at.save()

        etapa = AtendimentoEtapa.objects.create(
            atendimento=at,
            tipo=AtendimentoEtapa.Tipo.ABERTURA,
            autor=request.user,
            departamento=request.user.department,
            descricao=at.descricao or 'Atendimento aberto.',
        )
        try:
            _salvar_anexo(request.FILES.get('arquivo'), at, etapa, request.user)
        except ValidationError as e:
            messages.error(request, e.message)
            at.delete()
            return render(request, 'atendimento/create.html', {'form': form})

        # Encaminhamento automático baseado na fila
        _encaminhar_automatico(at, request.user)

        if at.nextqs_fila:
            from .nextqs import emitir_senha
            ok, ticket = emitir_senha(at)
            if ok:
                messages.success(request, f'Atendimento aberto. Senha {ticket} enviada para impressão.')
            else:
                messages.warning(request, f'Atendimento criado, mas erro na emissão NextQS: {ticket}')
        else:
            messages.success(request, 'Atendimento aberto com sucesso.')

        AuditLog.log(
            request.user, AuditLog.Action.ATENDIMENTO_CREATE,
            resource_type='Atendimento', resource_id=at.pk,
            ip=AuditMiddleware.get_client_ip(request),
        )
        return redirect('atendimento:detail', pk=at.pk)

    return render(request, 'atendimento/create.html', {'form': form})


@login_required
def atendimento_detail(request, pk):
    at = get_object_or_404(_qs_visivel(request.user), pk=pk)
    pode_agir = _pode_agir(at, request.user)
    ativo = at.status not in (Atendimento.Status.CONCLUIDO, Atendimento.Status.CANCELADO)

    nota_form = EtapaNotaForm()
    encaminhar_form = EncaminharForm()
    concluir_form = ConcluirForm()

    if request.method == 'POST' and pode_agir and ativo:
        action = request.POST.get('action')

        if action == 'nota':
            nota_form = EtapaNotaForm(request.POST, request.FILES)
            if nota_form.is_valid():
                etapa = AtendimentoEtapa.objects.create(
                    atendimento=at,
                    tipo=AtendimentoEtapa.Tipo.NOTA,
                    autor=request.user,
                    departamento=request.user.department,
                    descricao=nota_form.cleaned_data['descricao'],
                )
                _salvar_anexo(request.FILES.get('arquivo'), at, etapa, request.user)
                AuditLog.log(
                    request.user, AuditLog.Action.ATENDIMENTO_UPDATE,
                    resource_type='Atendimento', resource_id=at.pk,
                    ip=AuditMiddleware.get_client_ip(request),
                )
                return redirect('atendimento:detail', pk=at.pk)

        elif action == 'encaminhar':
            encaminhar_form = EncaminharForm(request.POST)
            if encaminhar_form.is_valid():
                para_dept = encaminhar_form.cleaned_data['para_departamento']
                obs = encaminhar_form.cleaned_data.get('descricao', '')
                AtendimentoEtapa.objects.create(
                    atendimento=at,
                    tipo=AtendimentoEtapa.Tipo.ENCAMINHAMENTO,
                    autor=request.user,
                    departamento=request.user.department,
                    para_departamento=para_dept,
                    descricao=obs or f'Encaminhado para {para_dept.name}.',
                )
                at.departamento_atual = para_dept
                at.status = Atendimento.Status.ENCAMINHADO
                at.save(update_fields=['departamento_atual', 'status', 'updated_at'])
                _notificar_encaminhamento(at, para_dept, request.user)
                AuditLog.log(
                    request.user, AuditLog.Action.ATENDIMENTO_UPDATE,
                    resource_type='Atendimento', resource_id=at.pk,
                    ip=AuditMiddleware.get_client_ip(request),
                )
                return redirect('atendimento:detail', pk=at.pk)

        elif action == 'em_andamento':
            ts = now()
            AtendimentoEtapa.objects.create(
                atendimento=at,
                tipo=AtendimentoEtapa.Tipo.NOTA,
                autor=request.user,
                departamento=request.user.department,
                descricao=f'{request.user.get_full_name() or request.user.email} iniciou o atendimento.',
            )
            update_fields = ['status', 'responsavel', 'updated_at']
            at.status = Atendimento.Status.EM_ANDAMENTO
            at.responsavel = request.user
            if not at.iniciado_em:
                at.iniciado_em = ts
                update_fields.append('iniciado_em')
            at.save(update_fields=update_fields)
            return redirect('atendimento:detail', pk=at.pk)

        elif action == 'concluir':
            concluir_form = ConcluirForm(request.POST, request.FILES)
            if concluir_form.is_valid():
                etapa = AtendimentoEtapa.objects.create(
                    atendimento=at,
                    tipo=AtendimentoEtapa.Tipo.CONCLUSAO,
                    autor=request.user,
                    departamento=request.user.department,
                    descricao=concluir_form.cleaned_data['descricao'],
                )
                _salvar_anexo(request.FILES.get('arquivo'), at, etapa, request.user)
                ts = now()
                update_fields = ['status', 'concluido_em', 'updated_at']
                at.status = Atendimento.Status.CONCLUIDO
                at.concluido_em = ts
                if not at.iniciado_em:
                    at.iniciado_em = ts
                    update_fields.append('iniciado_em')
                at.save(update_fields=update_fields)
                AuditLog.log(
                    request.user, AuditLog.Action.ATENDIMENTO_CLOSE,
                    resource_type='Atendimento', resource_id=at.pk,
                    ip=AuditMiddleware.get_client_ip(request),
                )
                messages.success(request, 'Atendimento concluído.')
                return redirect('atendimento:detail', pk=at.pk)

        elif action == 'cancelar':
            motivo = request.POST.get('motivo', 'Cancelado.')
            AtendimentoEtapa.objects.create(
                atendimento=at,
                tipo=AtendimentoEtapa.Tipo.CANCELAMENTO,
                autor=request.user,
                departamento=request.user.department,
                descricao=motivo,
            )
            at.status = Atendimento.Status.CANCELADO
            at.save(update_fields=['status', 'updated_at'])
            if at.numero_senha and at.nextqs_fila:
                from .nextqs import cancelar_senha
                agent_id = request.user.nextqs_agent_id or getattr(settings, 'NEXTQS_SYSTEM_AGENT_ID', '')
                if agent_id:
                    ok, msg = cancelar_senha(at, agent_id)
                    if not ok:
                        messages.warning(request, f'Atendimento cancelado, mas erro ao remover senha NextQS: {msg}')
                else:
                    messages.warning(request, 'Atendimento cancelado. Remova a senha manualmente no NextQS.')
            messages.success(request, 'Atendimento cancelado.')
            return redirect('atendimento:detail', pk=at.pk)

    etapas = at.etapas.select_related(
        'autor', 'departamento', 'para_departamento'
    ).prefetch_related('anexos')
    return render(request, 'atendimento/detail.html', {
        'at': at,
        'etapas': etapas,
        'pode_agir': pode_agir,
        'ativo': ativo,
        'nota_form': nota_form,
        'encaminhar_form': encaminhar_form,
        'concluir_form': concluir_form,
        'tempo_espera': _fmt_min(at.tempo_espera_min),
        'tempo_atendimento': _fmt_min(at.tempo_atendimento_min),
    })


@login_required
def atendimento_imprimir_senha(request, pk):
    at = get_object_or_404(_qs_visivel(request.user), pk=pk)
    return render(request, 'atendimento/imprimir_senha.html', {'at': at})


@login_required
def nextqs_chamar(request, pk):
    at = get_object_or_404(_qs_visivel(request.user), pk=pk)
    if request.method != 'POST':
        return redirect('atendimento:detail', pk=pk)
    if not (at.numero_senha and at.nextqs_fila):
        messages.error(request, 'Este atendimento não tem número de senha NextQS.')
        return redirect('atendimento:detail', pk=pk)
    agent_id = request.user.nextqs_agent_id
    if not agent_id:
        messages.error(request, 'Configure seu Agent ID NextQS no seu perfil antes de chamar senhas.')
        return redirect('atendimento:detail', pk=pk)

    agent_id = request.user.nextqs_agent_id or getattr(settings, 'NEXTQS_SYSTEM_AGENT_ID', '')
    if not agent_id:
        messages.error(request, 'Agent ID não configurado. Contate o administrador do sistema.')
        return redirect('atendimento:detail', pk=pk)

    from .nextqs import chamar_senha
    ok, msg = chamar_senha(at, agent_id)
    if ok:
        ts = now()
        update_fields = ['status', 'responsavel', 'updated_at']
        at.status = Atendimento.Status.EM_ANDAMENTO
        if not at.responsavel:
            at.responsavel = request.user
        if not at.iniciado_em:
            at.iniciado_em = ts
            update_fields.append('iniciado_em')
        at.save(update_fields=update_fields)
        AtendimentoEtapa.objects.create(
            atendimento=at,
            tipo=AtendimentoEtapa.Tipo.NOTA,
            autor=request.user,
            departamento=request.user.department,
            descricao=f'Senha {at.nextqs_fila}{at.numero_senha} chamada. Atendimento iniciado por {request.user.get_full_name() or request.user.email}.',
        )
        messages.success(request, f'Senha {at.nextqs_fila}{at.numero_senha} chamada no display!')
    else:
        messages.error(request, f'Erro NextQS: {msg}')
    return redirect('atendimento:detail', pk=pk)


def _fila_nextqs_ao_vivo():
    if not getattr(settings, 'NEXTQS_API_KEY', ''):
        return []
    import requests as req
    site_id = getattr(settings, 'NEXTQS_SERVICE_DESK', '')
    if not site_id:
        return []
    try:
        r = req.get(
            f'{settings.NEXTQS_API_BASE}/v1/organization/reports/service/queue/{site_id}',
            headers={'Authorization': f'Bearer {settings.NEXTQS_API_KEY}'},
            timeout=5,
        )
        r.raise_for_status()
        data = r.json()
        items = data if isinstance(data, list) else data.get('data', data.get('items', []))
        result = []
        for item in items:
            alpha = item.get('ticket_alpha') or item.get('alpha', '')
            number = str(item.get('ticket_number') or item.get('number', ''))
            result.append({
                'senha': f'{alpha}{number}',
                'alpha': alpha,
                'numero': number,
                'nome': item.get('customer_name', ''),
            })
        return result
    except Exception:
        return []


@login_required
def atendimento_painel(request):
    hoje = localdate()
    base = _qs_visivel(request.user)
    triagem = list(base.filter(status=Atendimento.Status.TRIAGEM, created_at__date=hoje))
    encaminhados = list(base.filter(status=Atendimento.Status.ENCAMINHADO, created_at__date=hoje))
    em_andamento = list(base.filter(status=Atendimento.Status.EM_ANDAMENTO, created_at__date=hoje))
    concluidos = list(base.filter(status=Atendimento.Status.CONCLUIDO, concluido_em__date=hoje))

    fila_ao_vivo = _fila_nextqs_ao_vivo()
    senhas_registradas = {
        f'{at.nextqs_fila}{at.numero_senha}'
        for at in triagem + encaminhados + em_andamento + concluidos
        if at.nextqs_fila and at.numero_senha
    }
    fila_sem_atendimento = [t for t in fila_ao_vivo if t['senha'] not in senhas_registradas]

    agora = now()
    for at in em_andamento:
        if at.iniciado_em:
            at.espera_min = max(0, int((agora - at.iniciado_em).total_seconds() / 60))
        else:
            at.espera_min = None

    return render(request, 'atendimento/painel.html', {
        'triagem': triagem,
        'encaminhados': encaminhados,
        'em_andamento': em_andamento,
        'concluidos': concluidos,
        'hoje': hoje,
        'fila_ao_vivo': fila_ao_vivo,
        'fila_sem_atendimento': fila_sem_atendimento,
    })


@login_required
def atendimento_filiado(request, cpf_hash):
    qs = _qs_visivel(request.user).filter(cpf_hash=cpf_hash).order_by('-created_at')
    if not qs.exists():
        messages.error(request, 'Nenhum atendimento encontrado para este filiado.')
        return redirect('atendimento:list')
    primeiro = qs.last()
    ultimo = qs.first()
    return render(request, 'atendimento/filiado.html', {
        'atendimentos': qs,
        'total': qs.count(),
        'nome_filiado': ultimo.nome_filiado,
        'cpf_hash': cpf_hash,
        'cpf_display': ultimo.cpf,
        'primeiro': primeiro,
        'ultimo': ultimo,
    })


@login_required
def atendimento_metricas(request):
    periodo = request.GET.get('periodo', 'hoje')
    hoje = localdate()

    if periodo == 'semana':
        desde = hoje - timedelta(days=6)
    elif periodo == 'mes':
        desde = hoje.replace(day=1)
    else:
        desde = hoje
        periodo = 'hoje'

    base = _qs_visivel(request.user).filter(created_at__date__gte=desde)
    concluidos_qs = base.filter(
        status=Atendimento.Status.CONCLUIDO
    ).select_related('responsavel')

    total = base.count()
    total_concluidos = concluidos_qs.count()
    total_abertos = base.exclude(
        status__in=[Atendimento.Status.CONCLUIDO, Atendimento.Status.CANCELADO]
    ).count()

    esperas, servicos = [], []
    por_operador = defaultdict(lambda: {'n': 0, 'esperas': [], 'servicos': []})
    por_fila = defaultdict(int)
    fila_labels = dict(Atendimento._meta.get_field('nextqs_fila').choices)

    for at in concluidos_qs:
        if at.iniciado_em:
            e = (at.iniciado_em - at.created_at).total_seconds() / 60
            esperas.append(e)
        if at.iniciado_em and at.concluido_em:
            s = (at.concluido_em - at.iniciado_em).total_seconds() / 60
            servicos.append(s)
        if at.responsavel:
            nome = at.responsavel.get_full_name() or at.responsavel.email
            por_operador[nome]['n'] += 1
            if at.iniciado_em:
                por_operador[nome]['esperas'].append(
                    (at.iniciado_em - at.created_at).total_seconds() / 60
                )
            if at.iniciado_em and at.concluido_em:
                por_operador[nome]['servicos'].append(
                    (at.concluido_em - at.iniciado_em).total_seconds() / 60
                )
        if at.nextqs_fila:
            label = fila_labels.get(at.nextqs_fila, at.nextqs_fila)
            por_fila[label] += 1

    avg_espera = int(sum(esperas) / len(esperas)) if esperas else None
    avg_servico = int(sum(servicos) / len(servicos)) if servicos else None

    operadores = sorted([
        {
            'nome': nome,
            'n': d['n'],
            'avg_espera': _fmt_min(int(sum(d['esperas']) / len(d['esperas'])) if d['esperas'] else None),
            'avg_servico': _fmt_min(int(sum(d['servicos']) / len(d['servicos'])) if d['servicos'] else None),
        }
        for nome, d in por_operador.items()
    ], key=lambda x: x['n'], reverse=True)

    return render(request, 'atendimento/metricas.html', {
        'periodo': periodo,
        'desde': desde,
        'hoje': hoje,
        'total': total,
        'total_concluidos': total_concluidos,
        'total_abertos': total_abertos,
        'avg_espera': _fmt_min(avg_espera),
        'avg_servico': _fmt_min(avg_servico),
        'operadores': operadores,
        'por_fila': dict(sorted(por_fila.items(), key=lambda x: x[1], reverse=True)),
    })
