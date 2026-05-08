import json
from django.contrib import messages
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponseForbidden
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import CustomUser, Department, Team, LGPDConsent, AuditLog, Notification
from .forms import LoginForm, RegisterForm, UserCreateForm, UserEditForm, ProfileForm, TeamForm, DepartmentForm
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

def login_view(request):
    if request.user.is_authenticated:
        return redirect('core:dashboard')
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
            return redirect(request.GET.get('next', '/'))
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
    overdue_cards = alert_qs.filter(due_date__lt=today).order_by('due_date')[:10]
    upcoming_cards = alert_qs.filter(due_date__gte=today, due_date__lte=in_3_days).order_by('due_date')[:10]

    # Tarefas por departamento (só para admin/presidente)
    dept_stats = []
    if user.can_see_all:
        rows = (
            Card.objects.filter(column__board__department__isnull=False)
            .values('column__board__department__pk', 'column__board__department__name')
            .annotate(
                total=Count('id'),
                overdue=Count('id', filter=Q(due_date__lt=today)),
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
        ip = AuditMiddleware.get_client_ip(request)
        LGPDConsent.objects.create(user=request.user, ip_address=ip or '0.0.0.0')
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
def lgpd_export(request):
    user = request.user
    AuditLog.log(user, AuditLog.Action.DATA_EXPORT, ip=AuditMiddleware.get_client_ip(request))
    from mensagens.models import Message
    from kanban.models import Card
    data = {
        'dados_pessoais': {
            'username': user.username,
            'nome': user.get_full_name(),
            'email': user.email,
            'telefone': user.phone,
            'bio': user.bio,
            'departamento': str(user.department) if user.department else None,
            'cargo': user.get_role_display(),
            'data_cadastro': user.date_joined.isoformat(),
            'lgpd_consentimento': user.lgpd_consent_date.isoformat() if user.lgpd_consent_date else None,
        },
        'mensagens_enviadas': list(
            Message.objects.filter(sender=user, is_deleted=False).values('content', 'sent_at')
        ),
        'cards_criados': list(Card.objects.filter(creator=user).values('title', 'created_at')),
    }
    response = JsonResponse(data, json_dumps_params={'ensure_ascii': False, 'indent': 2})
    response['Content-Disposition'] = 'attachment; filename="meus_dados_lgpd.json"'
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
    users = CustomUser.objects.filter(is_approved=True).select_related('department').order_by('first_name', 'last_name')
    pending = CustomUser.objects.filter(is_approved=False, is_active=False).order_by('date_joined')
    return render(request, 'usuarios/list.html', {'users': users, 'pending': pending})


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
    old_department = target.department
    form = UserEditForm(request.POST or None, request.FILES or None, instance=target)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        # Regra 5: atualiza equipe de departamento quando o departamento muda
        new_department = user.department
        if old_department != new_department:
            if old_department:
                try:
                    old_team = old_department.team
                    old_team.members.remove(user)
                    if old_team.conversation:
                        old_team.conversation.participants.remove(user)
                except Department.team.RelatedObjectDoesNotExist:
                    pass
            if new_department:
                dept_team, _ = Team.objects.get_or_create(
                    department=new_department,
                    defaults={'name': new_department.name, 'is_protected': True},
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
    target.is_active = True
    target.is_approved = True
    target.save(update_fields=['is_active', 'is_approved'])
    _add_to_teams(target)
    AuditLog.log(
        request.user, AuditLog.Action.USER_APPROVE,
        resource_type='CustomUser', resource_id=target.pk,
        ip=AuditMiddleware.get_client_ip(request),
        target_email=target.email,
    )
    messages.success(request, f'Usuário {target.get_full_name() or target.email} aprovado.')
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

    if user.department:
        dept_team, _ = Team.objects.get_or_create(
            department=user.department,
            defaults={'name': user.department.name, 'is_protected': True},
        )
        dept_team.members.add(user)
        if dept_team.conversation:
            dept_team.conversation.participants.add(user)


# ── Departamentos ─────────────────────────────

@login_required
def department_list(request):
    if not request.user.can_manage_users:
        return HttpResponseForbidden()
    depts = Department.objects.select_related('leader').prefetch_related('users').order_by('name')
    return render(request, 'departamentos/list.html', {'depts': depts})


@login_required
def department_create(request):
    if not request.user.can_manage_users:
        return HttpResponseForbidden()
    form = DepartmentForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        dept = form.save()
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


# ── Notificações ──────────────────────────────

@login_required
def notification_list(request):
    notifs = request.user.notifications.select_related('actor').order_by('-created_at')[:50]
    # Mark all as read
    request.user.notifications.filter(is_read=False).update(is_read=True)
    return render(request, 'notificacoes/list.html', {'notifs': notifs})


@login_required
@require_POST
def notification_mark_read(request, pk):
    Notification.objects.filter(pk=pk, user=request.user).update(is_read=True)
    next_url = request.POST.get('next', request.META.get('HTTP_REFERER', '/'))
    return redirect(next_url)


@login_required
@require_POST
def notification_mark_all_read(request):
    request.user.notifications.filter(is_read=False).update(is_read=True)
    return redirect(request.META.get('HTTP_REFERER', '/'))


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
