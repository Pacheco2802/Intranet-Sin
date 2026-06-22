import json
from django.contrib import messages
from django.contrib.auth import login, logout, authenticate, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponseForbidden
from django.shortcuts import render, redirect, get_object_or_404, resolve_url
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .models import CustomUser, Department, Team, LGPDConsent, AuditLog, Notification, _anonymize_ip
from .forms import LoginForm, RegisterForm, UserCreateForm, UserEditForm, ProfileForm, TeamForm, DepartmentForm, ApproveUserForm, AdminPasswordResetForm, ChangeOwnPasswordForm
from .middleware import AuditMiddleware

# ──────────────────────────────────────────────
# REGRAS DE NEGÓCIO — EQUIPES
# ──────────────────────────────────────────────
# 1. Apenas ADMIN_TI pode criar, renomear, excluir equipes e adicionar/remover membros.
# 2. A Equipe Geral e as equipes de departamento são protegidas: não podem ser excluídas.
# 3. Todo usuário aprovado entra automaticamente na Equipe Geral.
# 4. Ao ser aprovado, o usuário entra na equipe do seu departamento (se houver).
# 5. Quando o departamento do usuário é alterado, ele sai da equipe anterior e entra na nova.
# 6. Cada equipe tem um chat de grupo criado automaticamente no primeiro acesso.
# 7. Ao adicionar/remover membro de equipe, ele é adicionado/removido do chat.
# 8. Ao excluir uma equipe manual, o chat é excluído junto.
# 9. Todos os membros de uma equipe podem ler e enviar mensagens no chat da equipe.
# ──────────────────────────────────────────────


# ── Auth ──────────────────────────────────────

def _post_login_dest(user):
    """Diretor restrito cai direto em 'Minhas atividades'; os demais, no dashboard."""
    if user.is_diretor_restrito:
        return resolve_url('financeiro:atividade_list')
    return resolve_url('core:dashboard')


def login_view(request):
    if request.user.is_authenticated:
        return redirect(_post_login_dest(request.user))
    form = LoginForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = authenticate(
            request,
            username=form.cleaned_data['email'],
            password=form.cleaned_data['password'],
        )
        if user:
            login(request, user)
            AuditLog.log(user, AuditLog.Action.LOGIN, ip=AuditMiddleware.get_client_ip(request))
            next_url = request.GET.get('next', '')
            if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
                next_url = _post_login_dest(user)
            return redirect(next_url)
        try:
            pending = CustomUser.objects.get(email__iexact=form.cleaned_data['email'])
            if not pending.is_approved:
                form.add_error(None, 'Sua conta ainda aguarda aprovação do administrador.')
            else:
                form.add_error(None, 'E-mail ou senha inválidos.')
        except CustomUser.DoesNotExist:
            form.add_error(None, 'E-mail ou senha inválidos.')
    return render(request, 'auth/login.html', {'form': form})


def register_view(request):
    if request.user.is_authenticated:
        return redirect('core:dashboard')
    form = RegisterForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        cd = form.cleaned_data
        username = CustomUser.generate_username(cd['email'])
        user = CustomUser.objects.create_user(
            username=username,
            email=cd['email'].lower(),
            password=cd['password1'],
            first_name=cd['first_name'],
            last_name=cd['last_name'],
            is_active=False,
            is_approved=False,
        )
        AuditLog.log(None, AuditLog.Action.USER_REGISTER,
                     resource_type='CustomUser', resource_id=user.pk,
                     ip=AuditMiddleware.get_client_ip(request),
                     email=user.email)
        messages.success(request, 'Cadastro realizado! Aguarde a aprovação do administrador.')
        return redirect('core:login')
    return render(request, 'auth/register.html', {'form': form})


@login_required
def logout_view(request):
    AuditLog.log(request.user, AuditLog.Action.LOGOUT, ip=AuditMiddleware.get_client_ip(request))
    logout(request)
    return redirect('core:login')


# ── Dashboard ─────────────────────────────────

@login_required
def dashboard(request):
    from comunicados.models import Comunicado
    from kanban.models import Card, Board
    from mensagens.models import Conversation
    from django.utils.timezone import now
    from datetime import timedelta
    from django.db.models import Q, Count

    user = request.user
    today = now().date()
    in_3_days = today + timedelta(days=3)

    comunicados = Comunicado.objects.filter(is_published=True).order_by('-is_pinned', '-published_at')[:5]

    my_cards_qs = Card.objects.filter(assignee=user, column__board__isnull=False).select_related('column__board', 'column')
    my_cards = my_cards_qs[:10]

    if user.can_see_all:
        alert_qs = Card.objects.filter(column__board__isnull=False).select_related('column__board', 'column')
    else:
        alert_qs = my_cards_qs
    overdue_cards = alert_qs.filter(due_date__lt=today, final_status='').order_by('due_date')[:10]
    upcoming_cards = alert_qs.filter(due_date__gte=today, due_date__lte=in_3_days).order_by('due_date')[:10]

    # Tarefas por departamento (só para admin/presidente)
    dept_stats = []
    if user.can_see_all:
        rows = (
            Card.objects.filter(column__board__department__isnull=False)
            .values('column__board__department__pk', 'column__board__department__name')
            .annotate(
                total=Count('id'),
                overdue=Count('id', filter=Q(due_date__lt=today, final_status='')),
            )
            .order_by('-total')[:12]
        )
        dept_stats = [
            {'name': r['column__board__department__name'], 'total': r['total'], 'overdue': r['overdue']}
            for r in rows
        ]

    raw_convs = Conversation.objects.filter(participants=user).order_by('-updated_at')[:5]
    my_convs = [
        {'conv': c, 'display_name': c.get_display_name(user), 'last_message': c.get_last_message()}
        for c in raw_convs
    ]

    context = {
        'comunicados': comunicados,
        'my_cards': my_cards,
        'overdue_cards': overdue_cards,
        'upcoming_cards': upcoming_cards,
        'dept_stats': dept_stats,
        'my_convs': my_convs,
        'today': today,
    }
    return render(request, 'dashboard/index.html', context)


# ── LGPD ──────────────────────────────────────

@login_required
def lgpd_consent(request):
    if request.user.lgpd_consent:
        return redirect('core:dashboard')
    if request.method == 'POST':
        if request.POST.get('accept') != 'on':
            messages.error(request, 'Você precisa marcar a caixa de leitura para prosseguir.')
            return render(request, 'lgpd/consent.html')
        ip = _anonymize_ip(AuditMiddleware.get_client_ip(request) or '0.0.0.0')
        LGPDConsent.objects.create(user=request.user, ip_address=ip)
        request.user.lgpd_consent = True
        request.user.lgpd_consent_date = timezone.now()
        request.user.save(update_fields=['lgpd_consent', 'lgpd_consent_date'])
        AuditLog.log(request.user, AuditLog.Action.LGPD_CONSENT, ip=ip)
        return redirect('core:dashboard')
    return render(request, 'lgpd/consent.html')


@login_required
def lgpd_policy(request):
    return render(request, 'lgpd/policy.html')


@login_required
@require_POST
def lgpd_request_deletion(request):
    """Registra solicitação formal de eliminação de dados (Art. 18, VI da LGPD)."""
    AuditLog.log(
        request.user, AuditLog.Action.DATA_EXPORT,
        resource_type='DeletionRequest',
        ip=AuditMiddleware.get_client_ip(request),
        motivo=request.POST.get('motivo', ''),
    )
    messages.success(
        request,
        'Sua solicitação de eliminação de dados foi registrada. '
        'O Encarregado (ti@sinsaudesp.org.br) entrará em contato em até 15 dias úteis.',
    )
    return redirect('core:lgpd_policy')


@login_required
def lgpd_export(request):
    from django.core.cache import cache
    user = request.user
    cache_key = f'lgpd_export_{user.pk}'
    if cache.get(cache_key):
        messages.error(request, 'Aguarde antes de exportar novamente.')
        return redirect('core:profile')
    cache.set(cache_key, True, 120)
    AuditLog.log(user, AuditLog.Action.DATA_EXPORT, ip=AuditMiddleware.get_client_ip(request))
    from mensagens.models import Message
    from kanban.models import Card, CardComment
    from django.utils import timezone as tz

    consentimentos = list(
        user.consents.values('policy_version', 'consent_date', 'ip_address')
    )
    for c in consentimentos:
        if c['consent_date']:
            c['consent_date'] = c['consent_date'].isoformat()

    audit_logs = list(
        AuditLog.objects.filter(user=user)
        .order_by('timestamp')
        .values('action', 'resource_type', 'resource_id', 'timestamp')
    )
    for entry in audit_logs:
        if entry['timestamp']:
            entry['timestamp'] = entry['timestamp'].isoformat()

    data = {
        'exportacao': {
            'gerada_em': tz.now().isoformat(),
            'titular': user.get_full_name() or user.email,
            'lei': 'Lei nº 13.709/2018 — LGPD',
            'controlador': 'SINSAÚDE-SP',
            'encarregado': 'ti@sinsaudesp.org.br',
        },
        'dados_cadastrais': {
            'nome': user.get_full_name(),
            'email': user.email,
            'telefone': user.phone or None,
            'data_de_nascimento': user.birth_date.isoformat() if user.birth_date else None,
            'bio': user.bio or None,
            'foto': user.avatar.url if user.avatar else None,
            'cargo': user.get_role_display(),
            'departamentos': [str(d) for d in user.departments.all()],
            'data_cadastro': user.date_joined.isoformat(),
            'ultimo_acesso': user.last_login.isoformat() if user.last_login else None,
        },
        'consentimentos_lgpd': consentimentos,
        'logs_de_auditoria': audit_logs,
        'mensagens_enviadas': list(
            Message.objects.filter(sender=user, is_deleted=False)
            .order_by('sent_at')
            .values('content', 'sent_at')
        ),
        'cards_criados': list(
            Card.objects.filter(creator=user)
            .order_by('created_at')
            .values('title', 'description', 'created_at')
        ),
        'cards_atribuidos': list(
            Card.objects.filter(assignee=user)
            .order_by('created_at')
            .values('title', 'created_at')
        ),
        'comentarios': list(
            CardComment.objects.filter(author=user)
            .order_by('created_at')
            .values('content', 'created_at')
        ),
    }
    response = JsonResponse(data, json_dumps_params={'ensure_ascii': False, 'indent': 2})
    response['Content-Disposition'] = (
        f'attachment; filename="dados_lgpd_{user.pk}_{tz.now().strftime("%Y%m%d")}.json"'
    )
    return response


# ── Perfil ────────────────────────────────────

@login_required
def profile(request):
    form = ProfileForm(request.POST or None, request.FILES or None, instance=request.user)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Perfil atualizado com sucesso.')
        return redirect('core:profile')
    return render(request, 'perfil/index.html', {'form': form})


# ── Usuários ──────────────────────────────────

@login_required
def user_list(request):
    if not request.user.can_manage_users:
        return HttpResponseForbidden()
    users = CustomUser.objects.filter(is_approved=True).prefetch_related('departments').order_by('first_name', 'last_name')
    pending = CustomUser.objects.filter(is_approved=False, is_active=False).order_by('date_joined')
    departments = Department.objects.all().order_by('name')
    return render(request, 'usuarios/list.html', {
        'users': users,
        'pending': pending,
        'departments': departments,
    })


@login_required
def user_create(request):
    if not request.user.can_manage_users:
        return HttpResponseForbidden()
    form = UserCreateForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save(commit=False)
        user.created_by = request.user
        user.is_approved = True
        user.set_password(form.cleaned_data['password1'])
        user.save()
        form.save_m2m()
        _add_to_teams(user)
        AuditLog.log(
            request.user, AuditLog.Action.USER_CREATE,
            resource_type='CustomUser', resource_id=user.pk,
            ip=AuditMiddleware.get_client_ip(request),
            target_username=user.username,
        )
        messages.success(request, f'Usuário {user} criado com sucesso.')
        return redirect('core:user_list')
    return render(request, 'usuarios/form.html', {'form': form, 'title': 'Novo Usuário'})


@login_required
def user_edit(request, pk):
    if not request.user.can_manage_users:
        return HttpResponseForbidden()
    target = get_object_or_404(CustomUser, pk=pk)
    old_dept_pks = set(target.departments.values_list('pk', flat=True))
    form = UserEditForm(request.POST or None, request.FILES or None, instance=target)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        new_dept_pks = set(user.departments.values_list('pk', flat=True))
        for pk in old_dept_pks - new_dept_pks:
            try:
                old_team = Department.objects.get(pk=pk).team
                old_team.members.remove(user)
                if old_team.conversation:
                    old_team.conversation.participants.remove(user)
            except Exception:
                pass
        for pk in new_dept_pks - old_dept_pks:
            dept = Department.objects.get(pk=pk)
            dept_team, _ = Team.objects.get_or_create(
                department=dept,
                defaults={'name': dept.name, 'is_protected': True},
            )
            dept_team.members.add(user)
            if dept_team.conversation:
                dept_team.conversation.participants.add(user)
        AuditLog.log(
            request.user, AuditLog.Action.USER_EDIT,
            resource_type='CustomUser', resource_id=target.pk,
            ip=AuditMiddleware.get_client_ip(request),
        )
        messages.success(request, f'Usuário {target} atualizado.')
        return redirect('core:user_list')
    return render(request, 'usuarios/form.html', {'form': form, 'title': f'Editar {target}', 'target': target})


@login_required
@require_POST
def user_deactivate(request, pk):
    if not request.user.can_manage_users:
        return HttpResponseForbidden()
    target = get_object_or_404(CustomUser, pk=pk)
    if target == request.user:
        messages.error(request, 'Você não pode desativar sua própria conta.')
        return redirect('core:user_list')
    anonymize = request.POST.get('anonymize') == '1'
    if anonymize:
        target.anonymize()
        AuditLog.log(
            request.user, AuditLog.Action.USER_ANONYMIZE,
            resource_type='CustomUser', resource_id=target.pk,
            ip=AuditMiddleware.get_client_ip(request),
        )
        messages.success(request, 'Usuário anonimizado conforme LGPD.')
    else:
        target.is_active = False
        target.save(update_fields=['is_active'])
        AuditLog.log(
            request.user, AuditLog.Action.USER_DEACTIVATE,
            resource_type='CustomUser', resource_id=target.pk,
            ip=AuditMiddleware.get_client_ip(request),
        )
        messages.success(request, f'Usuário {target} desativado.')
    return redirect('core:user_list')


@login_required
@require_POST
def user_approve(request, pk):
    if not request.user.can_manage_users:
        return HttpResponseForbidden()
    target = get_object_or_404(CustomUser, pk=pk, is_approved=False)
    form = ApproveUserForm(request.POST)
    if form.is_valid():
        target.role = form.cleaned_data['role']
    target.is_active = True
    target.is_approved = True
    target.save(update_fields=['is_active', 'is_approved', 'role'])
    if form.is_valid() and form.cleaned_data.get('department'):
        target.departments.add(form.cleaned_data['department'])
    _add_to_teams(target)
    AuditLog.log(
        request.user, AuditLog.Action.USER_APPROVE,
        resource_type='CustomUser', resource_id=target.pk,
        ip=AuditMiddleware.get_client_ip(request),
        target_email=target.email,
    )
    messages.success(request, f'Usuário {target.get_full_name() or target.email} aprovado como {target.get_role_display()}.')
    return redirect('core:user_list')


@login_required
@require_POST
def user_reject(request, pk):
    if not request.user.can_manage_users:
        return HttpResponseForbidden()
    target = get_object_or_404(CustomUser, pk=pk, is_approved=False)
    name = target.get_full_name() or target.email
    AuditLog.log(
        request.user, AuditLog.Action.USER_REJECT,
        resource_type='CustomUser', resource_id=target.pk,
        ip=AuditMiddleware.get_client_ip(request),
        target_email=target.email,
    )
    target.delete()
    messages.success(request, f'Cadastro de {name} rejeitado e removido.')
    return redirect('core:user_list')


@login_required
@require_POST
def user_reset_password(request, pk):
    if not request.user.can_manage_users:
        return HttpResponseForbidden()
    target = get_object_or_404(CustomUser, pk=pk)
    form = AdminPasswordResetForm(request.POST)
    if form.is_valid():
        target.set_password(form.cleaned_data['password1'])
        target.save(update_fields=['password'])
        AuditLog.log(
            request.user, AuditLog.Action.USER_PASSWORD_RESET,
            resource_type='CustomUser', resource_id=target.pk,
            ip=AuditMiddleware.get_client_ip(request),
            target_email=target.email,
        )
        messages.success(request, f'Senha de {target.get_full_name() or target.email} redefinida com sucesso.')
    else:
        for field_errors in form.errors.values():
            for error in field_errors:
                messages.error(request, error)
    return redirect('core:user_list')


@login_required
@require_POST
def change_own_password(request):
    form = ChangeOwnPasswordForm(request.user, request.POST)
    if form.is_valid():
        request.user.set_password(form.cleaned_data['password1'])
        request.user.save(update_fields=['password'])
        update_session_auth_hash(request, request.user)
        AuditLog.log(
            request.user, AuditLog.Action.USER_PASSWORD_RESET,
            resource_type='CustomUser', resource_id=request.user.pk,
            ip=AuditMiddleware.get_client_ip(request),
            changed_by='self',
        )
        messages.success(request, 'Senha alterada com sucesso.')
    else:
        for field_errors in form.errors.values():
            for error in field_errors:
                messages.error(request, error)
    return redirect('core:profile')


# ── Equipes ───────────────────────────────────

@login_required
def team_list(request):
    is_admin = request.user.can_manage_users
    if is_admin:
        teams = Team.objects.prefetch_related('members', 'department').all()
    else:
        teams = request.user.teams.prefetch_related('members', 'department').all()
    all_users = []
    if is_admin:
        all_users = CustomUser.objects.filter(is_active=True, is_approved=True).order_by('first_name', 'last_name')
    return render(request, 'equipes/list.html', {
        'teams': teams,
        'all_users': all_users,
        'is_admin': is_admin,
    })


@login_required
def team_create(request):
    # Regra 1: apenas ADMIN_TI
    if not request.user.can_manage_users:
        return HttpResponseForbidden()
    form = TeamForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        team = form.save(commit=False)
        team.is_protected = False
        team.save()
        messages.success(request, f'Equipe "{team.name}" criada.')
        return redirect('core:team_list')
    return render(request, 'equipes/form.html', {'form': form, 'title': 'Nova Equipe'})


@login_required
def team_edit(request, pk):
    # Regra 1: apenas ADMIN_TI
    if not request.user.can_manage_users:
        return HttpResponseForbidden()
    team = get_object_or_404(Team, pk=pk)
    form = TeamForm(request.POST or None, instance=team)
    if request.method == 'POST' and form.is_valid():
        old_name = team.name
        team = form.save()
        # Sincroniza nome do chat se existir
        if team.conversation and team.conversation.name != f'Equipe: {team.name}':
            team.conversation.name = f'Equipe: {team.name}'
            team.conversation.save(update_fields=['name'])
        messages.success(request, f'Equipe "{team.name}" atualizada.')
        return redirect('core:team_list')
    return render(request, 'equipes/form.html', {'form': form, 'title': f'Editar Equipe: {team.name}', 'team': team})


@login_required
@require_POST
def team_delete(request, pk):
    # Regra 1: apenas ADMIN_TI | Regra 2: protegidas não podem ser excluídas
    if not request.user.can_manage_users:
        return HttpResponseForbidden()
    team = get_object_or_404(Team, pk=pk)
    if team.is_protected:
        messages.error(request, f'A equipe "{team.name}" é protegida e não pode ser excluída.')
        return redirect('core:team_list')
    name = team.name
    # Regra 8: exclui o chat junto
    if team.conversation:
        team.conversation.delete()
    team.delete()
    messages.success(request, f'Equipe "{name}" excluída.')
    return redirect('core:team_list')


@login_required
def team_chat(request, pk):
    # Regra 9: apenas membros (ou admin) acessam o chat
    team = get_object_or_404(Team, pk=pk)
    if not request.user.can_manage_users and not team.members.filter(pk=request.user.pk).exists():
        return HttpResponseForbidden()
    # Regra 6: cria o chat no primeiro acesso
    conv = team.ensure_conversation()
    # Garante que o usuário admin está no chat mesmo que não seja membro formal
    if request.user.can_manage_users:
        conv.participants.add(request.user)
    return redirect('mensagens:conversation', pk=conv.pk)


@login_required
@require_POST
def team_add_member(request, pk):
    # Regra 1: apenas ADMIN_TI
    if not request.user.can_manage_users:
        return HttpResponseForbidden()
    team = get_object_or_404(Team, pk=pk)
    user_id = request.POST.get('user_id')
    if not user_id:
        messages.error(request, 'Selecione um usuário.')
        return redirect('core:team_list')
    member = get_object_or_404(CustomUser, pk=user_id, is_active=True, is_approved=True)
    team.members.add(member)
    # Regra 7: sincroniza com o chat
    if team.conversation:
        team.conversation.participants.add(member)
    messages.success(request, f'{member} adicionado à equipe {team}.')
    return redirect('core:team_list')


@login_required
@require_POST
def team_remove_member(request, pk, user_id):
    # Regra 1: apenas ADMIN_TI
    if not request.user.can_manage_users:
        return HttpResponseForbidden()
    team = get_object_or_404(Team, pk=pk)
    member = get_object_or_404(CustomUser, pk=user_id)
    team.members.remove(member)
    # Regra 7: sincroniza com o chat
    if team.conversation:
        team.conversation.participants.remove(member)
    messages.success(request, f'{member} removido da equipe {team}.')
    return redirect('core:team_list')


# ── Helpers ───────────────────────────────────

def _add_to_teams(user):
    """Regras 3 e 4: adiciona usuário à Equipe Geral e à equipe do seu departamento."""
    general, _ = Team.objects.get_or_create(
        is_general=True,
        defaults={'name': 'Geral', 'is_protected': True},
    )
    general.members.add(user)
    if general.conversation:
        general.conversation.participants.add(user)

    for dept in user.departments.all():
        dept_team, _ = Team.objects.get_or_create(
            department=dept,
            defaults={'name': dept.name, 'is_protected': True},
        )
        dept_team.members.add(user)
        if dept_team.conversation:
            dept_team.conversation.participants.add(user)


# ── Departamentos ─────────────────────────────

def _setup_department(dept, created_by):
    """Cria board com colunas padrão e equipe para o departamento."""
    from kanban.models import Board, Column
    board, board_created = Board.objects.get_or_create(
        department=dept,
        is_auto=True,
        defaults={'name': dept.name, 'created_by': created_by},
    )
    if board_created:
        Column.objects.bulk_create([
            Column(board=board, name='A Fazer',      order=0, color='#64748b', column_type=Column.ColumnType.A_FAZER),
            Column(board=board, name='Em Andamento', order=1, color='#3b82f6', column_type=Column.ColumnType.EM_ANDAMENTO),
            Column(board=board, name='Status Final', order=2, color='#22c55e', column_type=Column.ColumnType.STATUS_FINAL),
        ])
    Team.objects.get_or_create(
        department=dept,
        defaults={'name': dept.name, 'is_protected': True},
    )

@login_required
def department_list(request):
    if not request.user.can_manage_users:
        return HttpResponseForbidden()
    depts = Department.objects.prefetch_related('leaders', 'users', 'boards', 'team').order_by('name')
    dept_data = []
    for dept in depts:
        dept_data.append({
            'dept': dept,
            'has_auto_board': dept.boards.filter(is_auto=True).exists(),
            'auto_board': dept.boards.filter(is_auto=True).first(),
        })
    return render(request, 'departamentos/list.html', {'dept_data': dept_data})


@login_required
def department_create(request):
    if not request.user.can_manage_users:
        return HttpResponseForbidden()
    form = DepartmentForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        dept = form.save()
        _setup_department(dept, request.user)
        messages.success(request, f'Departamento "{dept.name}" criado. Board e equipe gerados automaticamente.')
        return redirect('core:department_list')
    return render(request, 'departamentos/form.html', {'form': form, 'title': 'Novo Departamento'})


@login_required
def department_edit(request, pk):
    if not request.user.can_manage_users:
        return HttpResponseForbidden()
    dept = get_object_or_404(Department, pk=pk)
    form = DepartmentForm(request.POST or None, instance=dept)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, f'Departamento "{dept.name}" atualizado.')
        return redirect('core:department_list')
    return render(request, 'departamentos/form.html', {'form': form, 'title': f'Editar: {dept.name}', 'dept': dept})


@login_required
@require_POST
def department_delete(request, pk):
    if not request.user.can_manage_users:
        return HttpResponseForbidden()
    dept = get_object_or_404(Department, pk=pk)
    if dept.users.exists():
        messages.error(request, f'Não é possível excluir "{dept.name}": há usuários neste departamento. Remova-os primeiro.')
        return redirect('core:department_list')
    name = dept.name
    dept.delete()
    messages.success(request, f'Departamento "{name}" excluído.')
    return redirect('core:department_list')


@login_required
@require_POST
def department_create_board(request, pk):
    if not request.user.can_manage_users:
        return HttpResponseForbidden()
    dept = get_object_or_404(Department, pk=pk)
    if dept.boards.filter(is_auto=True).exists():
        messages.error(request, f'O departamento "{dept.name}" já possui um kanban.')
        return redirect('core:department_list')
    _setup_department(dept, request.user)
    messages.success(request, f'Kanban criado para "{dept.name}".')
    return redirect('core:department_list')


# ── Notificações ──────────────────────────────

@login_required
def topbar_counts(request):
    from mensagens.models import Conversation
    unread = 0
    try:
        for conv in Conversation.objects.filter(participants=request.user):
            unread += conv.messages.filter(
                is_deleted=False
            ).exclude(reads__user=request.user).exclude(sender=request.user).count()
    except Exception:
        pass
    notif_qs = Notification.objects.filter(user=request.user, is_read=False)
    notif_count = notif_qs.count()
    latest = notif_qs.order_by('-created_at').first()
    return render(request, 'partials/topbar_counts.html', {
        'notification_count': notif_count,
        'unread_messages_count': unread,
        'latest_id': latest.pk if latest else 0,
        'latest_title': latest.title if latest else '',
        'latest_body': latest.body if latest else '',
        'latest_link': latest.link if latest else '',
    })


@login_required
def notification_list(request):
    # Não marca tudo como lido ao abrir: marca-se ao clicar (notification_go)
    # ou no botão "Marcar todas como lidas".
    notifs = request.user.notifications.select_related('actor').order_by('-created_at')[:50]
    return render(request, 'notificacoes/list.html', {'notifs': notifs})


@login_required
def notification_dropdown(request):
    """Últimas notificações (lidas + não lidas) para o dropdown do sino."""
    notifs = request.user.notifications.select_related('actor').order_by('-created_at')[:10]
    return render(request, 'notificacoes/partials/dropdown.html', {'notifs': notifs})


@login_required
def notification_go(request, pk):
    """Marca uma notificação como lida e redireciona para o seu link."""
    notif = get_object_or_404(Notification, pk=pk, user=request.user)
    if not notif.is_read:
        notif.is_read = True
        notif.save(update_fields=['is_read'])
    dest = notif.link or '/'
    if not url_has_allowed_host_and_scheme(dest, allowed_hosts={request.get_host()}):
        dest = '/'
    return redirect(dest)


@login_required
@require_POST
def notification_mark_read(request, pk):
    Notification.objects.filter(pk=pk, user=request.user).update(is_read=True)
    next_url = request.POST.get('next', request.META.get('HTTP_REFERER', '/'))
    if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        next_url = '/'
    return redirect(next_url)


@login_required
@require_POST
def notification_mark_all_read(request):
    request.user.notifications.filter(is_read=False).update(is_read=True)
    referer = request.META.get('HTTP_REFERER', '/')
    if not url_has_allowed_host_and_scheme(referer, allowed_hosts={request.get_host()}):
        referer = '/'
    return redirect(referer)


# ── Logs de Auditoria (ADMIN_TI only) ─────────

@login_required
def audit_log_list(request):
    if not request.user.can_manage_users:
        return HttpResponseForbidden()

    from django.db.models import Q

    qs = AuditLog.objects.select_related('user').order_by('-timestamp')

    # Filtros
    user_q = request.GET.get('user', '').strip()
    action_q = request.GET.get('action', '').strip()
    resource_q = request.GET.get('resource', '').strip()
    date_from = request.GET.get('date_from', '').strip()
    date_to = request.GET.get('date_to', '').strip()

    if user_q:
        qs = qs.filter(
            Q(user__first_name__icontains=user_q) |
            Q(user__last_name__icontains=user_q) |
            Q(user__email__icontains=user_q)
        )
    if action_q:
        qs = qs.filter(action=action_q)
    if resource_q:
        qs = qs.filter(
            Q(resource_type__icontains=resource_q) |
            Q(resource_id__icontains=resource_q)
        )
    if date_from:
        qs = qs.filter(timestamp__date__gte=date_from)
    if date_to:
        qs = qs.filter(timestamp__date__lte=date_to)

    total = qs.count()
    logs = qs[:200]

    return render(request, 'logs/list.html', {
        'logs': logs,
        'total': total,
        'action_choices': AuditLog.Action.choices,
        'filters': {
            'user': user_q,
            'action': action_q,
            'resource': resource_q,
            'date_from': date_from,
            'date_to': date_to,
        },
    })


@login_required
def visao_executiva(request):
    if not request.user.can_see_all:
        return HttpResponseForbidden()

    from datetime import timedelta
    from django.db.models import Count, Q
    from atendimento.models import Atendimento, AtendimentoEtapa
    from kanban.models import Card, Column, CardActivity

    now = timezone.now()
    today = now.date()
    mes_inicio = today.replace(day=1)
    h24_atras = now - timedelta(hours=24)

    lider_depts = request.user.departments.all() if request.user.is_lider else None

    # ── Atendimentos ──────────────────────────────
    ats_mes = Atendimento.objects.filter(created_at__date__gte=mes_inicio)
    ats_base = Atendimento.objects
    if lider_depts is not None:
        ats_mes = ats_mes.filter(departamento_atual__in=lider_depts)
        ats_base = ats_base.filter(departamento_atual__in=lider_depts)

    at_total_mes      = ats_mes.count()
    at_concluidos_mes = ats_mes.filter(status='CONCLUIDO').count()
    at_cancelados_mes = ats_mes.filter(status='CANCELADO').count()
    at_ativos         = ats_base.exclude(status__in=['CONCLUIDO', 'CANCELADO']).count()
    at_recepcao       = ats_base.filter(status='TRIAGEM').count()
    at_encaminhados   = ats_base.filter(status='ENCAMINHADO').count()
    at_em_andamento   = ats_base.filter(status='EM_ANDAMENTO').count()

    # Tempo médio de conclusão (horas) — mês atual
    concluidos_mes = ats_mes.filter(status='CONCLUIDO', concluido_em__isnull=False)
    tempo_medio_horas = None
    if concluidos_mes.exists():
        total_seg = sum(
            (a.concluido_em - a.created_at).total_seconds()
            for a in concluidos_mes
        )
        tempo_medio_horas = round(total_seg / concluidos_mes.count() / 3600, 1)

    # Atendimentos ativos por departamento
    at_por_dept_qs = (
        Atendimento.objects
        .exclude(status__in=['CONCLUIDO', 'CANCELADO'])
        .exclude(departamento_atual__isnull=True)
    )
    if lider_depts is not None:
        at_por_dept_qs = at_por_dept_qs.filter(departamento_atual__in=lider_depts)
    at_por_dept = (
        at_por_dept_qs
        .values('departamento_atual__name', 'departamento_atual__icon', 'departamento_atual__pk')
        .annotate(total=Count('id'))
        .order_by('-total')
    )

    # ── Kanban ────────────────────────────────────
    CT = Column.ColumnType
    cards_base = Card.objects
    if lider_depts is not None:
        cards_base = cards_base.filter(column__board__department__in=lider_depts)
    cards_ativos = cards_base.exclude(column__column_type=CT.STATUS_FINAL)

    urgentes = (
        cards_ativos
        .filter(priority__in=['URGENT', 'HIGH'])
        .select_related('column__board__department', 'assignee')
        .order_by('priority', 'due_date')[:12]
    )

    vencidos_lista = (
        cards_ativos
        .filter(due_date__lt=today, due_date__isnull=False, final_status='')
        .select_related('column__board__department', 'assignee')
        .order_by('due_date')[:20]
    )

    # Saúde por departamento
    dept_saude = []
    depts_iter = lider_depts.order_by('name') if lider_depts is not None else Department.objects.order_by('name')
    for dept in depts_iter:
        dc = Card.objects.filter(column__board__department=dept)
        total_dept   = dc.count()
        ativos_dept  = dc.exclude(column__column_type=CT.STATUS_FINAL).count()
        venc_dept    = dc.exclude(column__column_type=CT.STATUS_FINAL).filter(
            due_date__lt=today, due_date__isnull=False, final_status=''
        ).count()
        em_and_dept  = dc.filter(column__column_type=CT.EM_ANDAMENTO).count()
        concl_dept   = dc.filter(column__column_type=CT.STATUS_FINAL).count()

        if total_dept == 0:
            continue

        if venc_dept == 0:
            saude = 'green'
        elif ativos_dept > 0 and venc_dept / ativos_dept >= 0.3:
            saude = 'red'
        else:
            saude = 'yellow'

        dept_saude.append({
            'dept': dept,
            'ativos': ativos_dept,
            'vencidos': venc_dept,
            'em_andamento': em_and_dept,
            'concluidos': concl_dept,
            'saude': saude,
        })

    # ── Atividade 24h ─────────────────────────────
    kanban_ativ_qs = CardActivity.objects.filter(timestamp__gte=h24_atras)
    etapas_qs = AtendimentoEtapa.objects.filter(
        created_at__gte=h24_atras, tipo__in=['ABERTURA', 'CONCLUSAO', 'CANCELAMENTO']
    )
    if lider_depts is not None:
        kanban_ativ_qs = kanban_ativ_qs.filter(card__column__board__department__in=lider_depts)
        etapas_qs = etapas_qs.filter(atendimento__departamento_atual__in=lider_depts)

    atividade_kanban = (
        kanban_ativ_qs
        .select_related('card__column__board', 'user')
        .order_by('-timestamp')[:20]
    )

    etapas_recentes = (
        etapas_qs
        .select_related('atendimento', 'autor')
        .order_by('-created_at')[:20]
    )

    return render(request, 'core/visao_executiva.html', {
        'at_total_mes':      at_total_mes,
        'at_concluidos_mes': at_concluidos_mes,
        'at_cancelados_mes': at_cancelados_mes,
        'at_ativos':         at_ativos,
        'at_recepcao':       at_recepcao,
        'at_encaminhados':   at_encaminhados,
        'at_em_andamento':   at_em_andamento,
        'tempo_medio_horas': tempo_medio_horas,
        'at_por_dept':       at_por_dept,
        'urgentes':          urgentes,
        'vencidos_lista':    vencidos_lista,
        'dept_saude':        dept_saude,
        'atividade_kanban':  atividade_kanban,
        'etapas_recentes':   etapas_recentes,
        'mes_inicio':        mes_inicio,
    })
