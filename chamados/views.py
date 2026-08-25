import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponseForbidden
from django.shortcuts import render, redirect, get_object_or_404
from django.utils.timezone import now

from core.models import AuditLog, Notification, CustomUser
from core.middleware import AuditMiddleware

from .models import (
    Chamado, ChamadoEtapa, ChamadoAnexo,
    CategoriaChamado, PerguntaTriagem, OpcaoTriagem, Prioridade,
)
from .forms import (
    ChamadoFinalForm, ChamadoManualForm, ComentarioForm, ChamadoFilterForm,
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _is_ti(user):
    """Membro da equipe de TI que atende chamados (Administrador TI) ou liderança
    com visão ampla."""
    return user.is_admin_ti or user.can_see_all


def _pode_ver(chamado, user):
    return chamado.solicitante_id == user.pk or _is_ti(user)


def _salvar_anexo(arquivo, chamado, etapa, user):
    if not arquivo:
        return None
    return ChamadoAnexo.objects.create(
        chamado=chamado, etapa=etapa, arquivo=arquivo,
        nome_original=arquivo.name, enviado_por=user,
    )


def _equipe_ti():
    """Usuários que devem ser notificados de novos chamados."""
    return CustomUser.objects.filter(
        role=CustomUser.Role.ADMIN_TI, is_active=True, is_approved=True,
    )


def _notificar_ti(chamado, actor):
    for user in _equipe_ti():
        Notification.send(
            user=user, actor=actor,
            ntype=Notification.Type.CHAMADO_NOVO,
            title=f'Novo chamado {chamado.codigo}',
            body=f'{chamado.get_prioridade_display()} — {chamado.titulo}',
            link=f'/chamados/{chamado.pk}/',
        )


def _caminho_opcoes(caminho_raw):
    """Recebe o JSON de ids de OpcaoTriagem percorridas e devolve as instâncias
    na ordem original, validando que existem."""
    try:
        ids = json.loads(caminho_raw or '[]')
    except (ValueError, TypeError):
        ids = []
    ids = [int(i) for i in ids if str(i).isdigit()]
    mapa = OpcaoTriagem.objects.select_related('pergunta', 'categoria').in_bulk(ids)
    return [mapa[i] for i in ids if i in mapa]


# --------------------------------------------------------------------------- #
# Abertura — assistente guiado (wizard)
# --------------------------------------------------------------------------- #

@login_required
def chamado_abrir(request):
    """Inicia o assistente. Sem árvore configurada, cai no formulário manual."""
    raiz = PerguntaTriagem.raiz()
    if not raiz:
        return _abrir_manual(request)
    return render(request, 'chamados/abrir.html', {
        'pergunta': raiz,
        'opcoes': raiz.opcoes.select_related('categoria').all(),
        'caminho_json': '[]',
    })


def _abrir_manual(request):
    form = ChamadoManualForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        return _criar_chamado(
            request,
            categoria=form.cleaned_data['categoria'],
            prioridade=form.cleaned_data['categoria'].prioridade_padrao,
            titulo=form.cleaned_data['titulo'],
            descricao=form.cleaned_data['descricao'],
            respostas=[],
            arquivo=request.FILES.get('arquivo'),
        )
    return render(request, 'chamados/abrir_manual.html', {'form': form})


@login_required
def triagem_passo(request):
    """Recebe a opção escolhida (htmx) e devolve o próximo passo: outra pergunta
    ou o formulário final já com categoria/prioridade resolvidas."""
    if request.method != 'POST':
        return redirect('chamados:abrir')

    caminho = _caminho_opcoes(request.POST.get('caminho'))
    try:
        opcao = OpcaoTriagem.objects.select_related('categoria', 'proxima_pergunta').get(
            pk=request.POST.get('opcao_id')
        )
    except (OpcaoTriagem.DoesNotExist, ValueError):
        return redirect('chamados:abrir')

    caminho.append(opcao)
    caminho_json = json.dumps([o.pk for o in caminho])

    if opcao.is_folha:
        prioridade = opcao.prioridade_efetiva()
        return render(request, 'chamados/partials/final.html', {
            'form': ChamadoFinalForm(),
            'categoria': opcao.categoria,
            'prioridade': prioridade,
            'prioridade_label': Prioridade(prioridade).label,
            'respostas': [
                {'pergunta': o.pergunta.texto, 'resposta': o.label} for o in caminho
            ],
            'caminho_json': caminho_json,
        })

    proxima = opcao.proxima_pergunta
    return render(request, 'chamados/partials/passo.html', {
        'pergunta': proxima,
        'opcoes': proxima.opcoes.select_related('categoria').all(),
        'caminho_json': caminho_json,
        'trilha': [
            {'pergunta': o.pergunta.texto, 'resposta': o.label, 'icone': o.icone}
            for o in caminho
        ],
    })


@login_required
def chamado_criar(request):
    """Submit final do assistente: cria o chamado a partir do caminho percorrido."""
    if request.method != 'POST':
        return redirect('chamados:abrir')

    caminho = _caminho_opcoes(request.POST.get('caminho'))
    folha = caminho[-1] if caminho else None
    if not folha or not folha.is_folha:
        messages.error(request, 'Não foi possível identificar a categoria. Recomece o chamado.')
        return redirect('chamados:abrir')

    form = ChamadoFinalForm(request.POST, request.FILES)
    if not form.is_valid():
        prioridade = folha.prioridade_efetiva()
        return render(request, 'chamados/abrir.html', {
            'form': form,
            'categoria': folha.categoria,
            'prioridade': prioridade,
            'prioridade_label': Prioridade(prioridade).label,
            'respostas': [
                {'pergunta': o.pergunta.texto, 'resposta': o.label} for o in caminho
            ],
            'caminho_json': json.dumps([o.pk for o in caminho]),
        })

    return _criar_chamado(
        request,
        categoria=folha.categoria,
        prioridade=folha.prioridade_efetiva(),
        titulo=form.cleaned_data['titulo'],
        descricao=form.cleaned_data['descricao'],
        respostas=[{'pergunta': o.pergunta.texto, 'resposta': o.label} for o in caminho],
        arquivo=request.FILES.get('arquivo'),
    )


def _criar_chamado(request, *, categoria, prioridade, titulo, descricao, respostas, arquivo):
    chamado = Chamado.objects.create(
        solicitante=request.user,
        titulo=titulo,
        descricao=descricao,
        categoria=categoria,
        prioridade=prioridade,
        respostas_triagem=respostas,
    )
    if categoria and categoria.responsavel_padrao_id:
        chamado.responsavel_id = categoria.responsavel_padrao_id
        chamado.save(update_fields=['responsavel', 'updated_at'])

    etapa = ChamadoEtapa.objects.create(
        chamado=chamado,
        tipo=ChamadoEtapa.Tipo.ABERTURA,
        autor=request.user,
        descricao=descricao or 'Chamado aberto.',
    )
    try:
        _salvar_anexo(arquivo, chamado, etapa, request.user)
    except ValidationError as e:
        messages.warning(request, f'Chamado criado, mas o anexo foi rejeitado: {e.message}')

    _notificar_ti(chamado, request.user)
    AuditLog.log(
        request.user, AuditLog.Action.CHAMADO_CREATE,
        resource_type='Chamado', resource_id=chamado.pk,
        ip=AuditMiddleware.get_client_ip(request),
    )
    messages.success(request, f'Chamado {chamado.codigo} aberto com sucesso.')
    return redirect('chamados:detail', pk=chamado.pk)


# --------------------------------------------------------------------------- #
# Listas
# --------------------------------------------------------------------------- #

@login_required
def meus_chamados(request):
    qs = Chamado.objects.filter(solicitante=request.user).select_related('categoria')
    return render(request, 'chamados/meus_chamados.html', {
        'chamados': qs,
        'abertos': qs.filter(status__in=[
            Chamado.Status.ABERTO, Chamado.Status.EM_ANDAMENTO, Chamado.Status.AGUARDANDO,
        ]).count(),
    })


@login_required
def painel(request):
    """Fila da equipe de TI."""
    if not _is_ti(request.user):
        return HttpResponseForbidden()

    qs = Chamado.objects.select_related('categoria', 'solicitante', 'responsavel')
    form = ChamadoFilterForm(request.GET or None)
    if form.is_valid():
        q = form.cleaned_data.get('q', '').strip()
        status = form.cleaned_data.get('status', '')
        categoria = form.cleaned_data.get('categoria')
        prioridade = form.cleaned_data.get('prioridade', '')
        if q:
            qs = qs.filter(Q(codigo__icontains=q) | Q(titulo__icontains=q))
        if status:
            qs = qs.filter(status=status)
        if categoria:
            qs = qs.filter(categoria=categoria)
        if prioridade:
            qs = qs.filter(prioridade=prioridade)

    abertos = qs.filter(status__in=[
        Chamado.Status.ABERTO, Chamado.Status.EM_ANDAMENTO, Chamado.Status.AGUARDANDO,
    ]).count()

    paginator = Paginator(qs, 30)
    page_obj = paginator.get_page(request.GET.get('page', 1))
    params = request.GET.copy()
    params.pop('page', None)

    return render(request, 'chamados/painel.html', {
        'chamados': page_obj,
        'page_obj': page_obj,
        'form': form,
        'abertos': abertos,
        'total': qs.count(),
        'base_query': params.urlencode(),
    })


# --------------------------------------------------------------------------- #
# Detalhe + ações
# --------------------------------------------------------------------------- #

@login_required
def chamado_detail(request, pk):
    chamado = get_object_or_404(
        Chamado.objects.select_related('categoria', 'solicitante', 'responsavel'), pk=pk,
    )
    if not _pode_ver(chamado, request.user):
        return HttpResponseForbidden()

    is_ti = _is_ti(request.user)
    comentario_form = ComentarioForm()

    if request.method == 'POST':
        action = request.POST.get('action')

        # Comentar: solicitante e TI podem
        if action == 'comentar':
            comentario_form = ComentarioForm(request.POST, request.FILES)
            if comentario_form.is_valid():
                etapa = ChamadoEtapa.objects.create(
                    chamado=chamado,
                    tipo=ChamadoEtapa.Tipo.COMENTARIO,
                    autor=request.user,
                    descricao=comentario_form.cleaned_data['descricao'],
                )
                _salvar_anexo(request.FILES.get('arquivo'), chamado, etapa, request.user)
                _notificar_contraparte(
                    chamado, request.user, Notification.Type.CHAMADO_COMENTARIO,
                    f'Novo comentário no chamado {chamado.codigo}',
                    comentario_form.cleaned_data['descricao'][:120],
                )
                AuditLog.log(
                    request.user, AuditLog.Action.CHAMADO_UPDATE,
                    resource_type='Chamado', resource_id=chamado.pk,
                    ip=AuditMiddleware.get_client_ip(request),
                )
                return redirect('chamados:detail', pk=chamado.pk)

        # Reabrir: o solicitante pode reabrir um chamado resolvido
        elif action == 'reabrir' and chamado.solicitante_id == request.user.pk:
            if chamado.status in (Chamado.Status.RESOLVIDO, Chamado.Status.FECHADO):
                chamado.status = Chamado.Status.ABERTO
                chamado.resolvido_em = None
                chamado.save(update_fields=['status', 'resolvido_em', 'updated_at'])
                ChamadoEtapa.objects.create(
                    chamado=chamado, tipo=ChamadoEtapa.Tipo.REABERTURA, autor=request.user,
                    descricao=request.POST.get('motivo', '').strip() or 'Chamado reaberto pelo solicitante.',
                )
                _notificar_ti(chamado, request.user)
                messages.success(request, 'Chamado reaberto.')
            return redirect('chamados:detail', pk=chamado.pk)

        # Ações exclusivas da TI
        elif is_ti and action == 'assumir':
            chamado.responsavel = request.user
            if chamado.status == Chamado.Status.ABERTO:
                chamado.status = Chamado.Status.EM_ANDAMENTO
                if not chamado.iniciado_em:
                    chamado.iniciado_em = now()
            chamado.save(update_fields=['responsavel', 'status', 'iniciado_em', 'updated_at'])
            ChamadoEtapa.objects.create(
                chamado=chamado, tipo=ChamadoEtapa.Tipo.ATRIBUICAO, autor=request.user,
                descricao=f'{request.user.get_full_name() or request.user.email} assumiu o chamado.',
            )
            _notificar_contraparte(
                chamado, request.user, Notification.Type.CHAMADO_STATUS,
                f'Seu chamado {chamado.codigo} está em andamento',
                'A equipe de TI começou a atender.',
            )
            return redirect('chamados:detail', pk=chamado.pk)

        elif is_ti and action == 'status':
            novo = request.POST.get('status')
            if novo in Chamado.Status.values and novo != chamado.status:
                _mudar_status(chamado, novo, request.user, request.POST.get('descricao', '').strip())
                AuditLog.log(
                    request.user,
                    AuditLog.Action.CHAMADO_CLOSE if novo == Chamado.Status.RESOLVIDO else AuditLog.Action.CHAMADO_UPDATE,
                    resource_type='Chamado', resource_id=chamado.pk,
                    ip=AuditMiddleware.get_client_ip(request),
                )
            return redirect('chamados:detail', pk=chamado.pk)

    etapas = chamado.etapas.select_related('autor').prefetch_related('anexos')
    return render(request, 'chamados/detail.html', {
        'chamado': chamado,
        'etapas': etapas,
        'anexos_gerais': chamado.anexos.filter(etapa__isnull=True),
        'is_ti': is_ti,
        'comentario_form': comentario_form,
        'status_choices': Chamado.Status.choices,
    })


def _mudar_status(chamado, novo, autor, obs):
    anterior = chamado.get_status_display()
    chamado.status = novo
    update_fields = ['status', 'updated_at']
    if novo == Chamado.Status.RESOLVIDO and not chamado.resolvido_em:
        chamado.resolvido_em = now()
        update_fields.append('resolvido_em')
    if novo in (Chamado.Status.EM_ANDAMENTO,) and not chamado.iniciado_em:
        chamado.iniciado_em = now()
        update_fields.append('iniciado_em')
    chamado.save(update_fields=update_fields)

    tipo = {
        Chamado.Status.RESOLVIDO: ChamadoEtapa.Tipo.RESOLUCAO,
        Chamado.Status.CANCELADO: ChamadoEtapa.Tipo.CANCELAMENTO,
    }.get(novo, ChamadoEtapa.Tipo.STATUS)
    ChamadoEtapa.objects.create(
        chamado=chamado, tipo=tipo, autor=autor,
        descricao=obs or f'Status alterado de "{anterior}" para "{chamado.get_status_display()}".',
    )
    _notificar_contraparte(
        chamado, autor, Notification.Type.CHAMADO_STATUS,
        f'Chamado {chamado.codigo}: {chamado.get_status_display()}',
        obs[:120] if obs else '',
    )


def _notificar_contraparte(chamado, actor, ntype, title, body):
    """Notifica o solicitante quando a TI age, e o responsável quando o solicitante age."""
    alvos = set()
    if actor.pk != chamado.solicitante_id and chamado.solicitante_id:
        alvos.add(chamado.solicitante)
    if chamado.responsavel_id and chamado.responsavel_id != actor.pk:
        alvos.add(chamado.responsavel)
    for user in alvos:
        Notification.send(
            user=user, actor=actor, ntype=ntype,
            title=title, body=body, link=f'/chamados/{chamado.pk}/',
        )
