from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpResponseForbidden
from django.shortcuts import render, redirect, get_object_or_404
from django.utils.timezone import now

from core.models import AuditLog, Notification, CustomUser
from core.middleware import AuditMiddleware
from kanban.utils import criar_card_automatico
from .models import Atendimento, AtendimentoEtapa, AtendimentoAnexo
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
        Q(criado_por=user) | Q(departamento_atual=user.department)
    ).distinct()


def _pode_agir(atendimento, user):
    if user.can_see_all:
        return True
    if atendimento.criado_por == user:
        return True
    if user.department and atendimento.departamento_atual == user.department:
        return True
    return False


def _salvar_anexo(arquivo, atendimento, etapa, user):
    if arquivo:
        AtendimentoAnexo.objects.create(
            atendimento=atendimento,
            etapa=etapa,
            arquivo=arquivo,
            nome_original=arquivo.name,
            enviado_por=user,
        )


def _notificar_encaminhamento(atendimento, para_dept, actor):
    link = f'/atendimento/{atendimento.pk}/'
    targets = set()
    if para_dept.leader and para_dept.leader != actor:
        targets.add(para_dept.leader)
    for mgr in CustomUser.objects.filter(
        role=CustomUser.Role.GERENTE, department=para_dept, is_active=True
    ):
        if mgr != actor:
            targets.add(mgr)
    for user in targets:
        Notification.send(
            user=user, actor=actor,
            ntype=Notification.Type.CARD_CROSS,
            title=f'Atendimento encaminhado para {para_dept.name}',
            body=f'{atendimento.nome_filiado} — {atendimento.assunto}',
            link=link,
        )


@login_required
def atendimento_list(request):
    qs = _qs_visivel(request.user)
    form = AtendimentoFilterForm(request.GET or None)
    cpf_filtro = ''

    if form.is_valid():
        cpf = form.cleaned_data.get('cpf', '').strip()
        nome = form.cleaned_data.get('nome', '').strip()
        status = form.cleaned_data.get('status', '')
        departamento = form.cleaned_data.get('departamento')

        if cpf:
            cpf_filtro = cpf
            cpf_limpo = ''.join(c for c in cpf if c.isdigit())
            qs = _qs_visivel(request.user).filter(
                Q(cpf__icontains=cpf) | Q(cpf__icontains=cpf_limpo)
            ).distinct()
        if nome:
            qs = qs.filter(nome_filiado__icontains=nome)
        if status:
            qs = qs.filter(status=status)
        if departamento:
            qs = qs.filter(departamento_atual=departamento)

    total = qs.count()
    return render(request, 'atendimento/list.html', {
        'atendimentos': qs[:50],
        'form': form,
        'cpf_filtro': cpf_filtro,
        'total': total,
    })


@login_required
def atendimento_create(request):
    form = AtendimentoForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        at = form.save(commit=False)
        at.criado_por = request.user
        at.departamento_atual = request.user.department
        at.save()

        etapa = AtendimentoEtapa.objects.create(
            atendimento=at,
            tipo=AtendimentoEtapa.Tipo.ABERTURA,
            autor=request.user,
            departamento=request.user.department,
            descricao=at.descricao or 'Atendimento aberto.',
        )
        _salvar_anexo(request.FILES.get('arquivo'), at, etapa, request.user)

        criar_card_automatico(
            department=at.departamento_atual,
            title=f'Atendimento: {at.assunto}',
            description=f'Filiado: {at.nome_filiado}\nCPF: {at.cpf}\n\n{at.descricao or ""}',
            creator=request.user,
            tags='atendimento',
            atendimento_id=at.pk,
        )

        AuditLog.log(
            request.user, AuditLog.Action.ATENDIMENTO_CREATE,
            resource_type='Atendimento', resource_id=at.pk,
            ip=AuditMiddleware.get_client_ip(request),
        )
        messages.success(request, 'Atendimento aberto com sucesso.')
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
            AtendimentoEtapa.objects.create(
                atendimento=at,
                tipo=AtendimentoEtapa.Tipo.NOTA,
                autor=request.user,
                departamento=request.user.department,
                descricao=f'{request.user.get_full_name() or request.user.email} iniciou o atendimento.',
            )
            at.status = Atendimento.Status.EM_ANDAMENTO
            at.responsavel = request.user
            at.save(update_fields=['status', 'responsavel', 'updated_at'])
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
                at.status = Atendimento.Status.CONCLUIDO
                at.concluido_em = now()
                at.save(update_fields=['status', 'concluido_em', 'updated_at'])
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
    })
