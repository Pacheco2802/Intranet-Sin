import json
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Count, Q
from django.db.models import Prefetch
from django.http import JsonResponse, HttpResponseForbidden
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.models import AuditLog, Notification, CustomUser, Department
from core.middleware import AuditMiddleware
from core.validators import validate_file_extension, validate_file_size
from .models import Board, BoardFolder, Column, Card, CardComment, CardActivity, SubTask, SubTaskAnexo, CardAnexo, RecurringTask, PastaDocumento, PastaPost
from .forms import BoardForm, BoardFolderForm, ProjectForm, ColumnForm, CardForm, CardCommentForm, SubTaskForm, RecurringTaskForm
from .utils import criar_card_automatico, mover_card_para_ultima_coluna, mover_card_para_primeira_coluna, build_grouped_columns


@login_required
def board_list(request):
    user = request.user
    if user.can_see_all:
        boards = Board.objects.all().select_related('department', 'created_by')
    else:
        from django.db.models import Q
        boards = Board.objects.filter(
            Q(department__in=user.departments.all()) |
            Q(members=user) |
            Q(is_global=True)
        ).distinct().select_related('department', 'created_by')
    # Separate global board for easier template use
    global_board = boards.filter(is_global=True).first()
    dept_boards = boards.filter(is_global=False, is_cross_department=False, is_auto=True)
    project_boards = boards.filter(is_global=False, is_cross_department=True)
    manual_boards = boards.filter(is_global=False, is_auto=False, is_cross_department=False)
    return render(request, 'kanban/list.html', {
        'boards': boards,
        'global_board': global_board,
        'dept_boards': dept_boards,
        'project_boards': project_boards,
        'manual_boards': manual_boards,
    })


# ───────────────────────── Pastas por departamento ─────────────────────────

def pode_gerenciar_pastas(user, dept):
    """Quem pode criar/editar pastas e quadros dentro de um departamento:
    admin TI, presidente/coord geral e líderes do próprio departamento."""
    return user.is_admin_ti or user.is_presidente or dept.leaders.filter(pk=user.pk).exists()


def _pode_ver_departamento(user, dept):
    return user.can_see_all or user.departments.filter(pk=dept.pk).exists()


@login_required
def departamentos(request):
    """Home do Kanban: departamentos que o usuário acessa, como 'pastas'."""
    user = request.user
    if user.can_see_all:
        depts = Department.objects.all()
    else:
        depts = user.departments.all()
    depts = depts.prefetch_related('boards', 'board_folders').order_by('name')
    data = []
    for dept in depts:
        boards_acessiveis = [b for b in dept.boards.all() if b.can_access(user)]
        data.append({
            'dept': dept,
            'n_boards': len(boards_acessiveis),
            'n_folders': dept.board_folders.count(),
            'pode_gerenciar': pode_gerenciar_pastas(user, dept),
        })
    return render(request, 'kanban/pastas_home.html', {'departamentos': data})


@login_required
def departamento(request, dept_pk):
    """Pastas de um departamento + grupo 'Geral' (quadros sem pasta)."""
    user = request.user
    dept = get_object_or_404(Department, pk=dept_pk)
    if not _pode_ver_departamento(user, dept):
        return HttpResponseForbidden()
    pode = pode_gerenciar_pastas(user, dept)
    folders = []
    for f in dept.board_folders.prefetch_related('boards').all():
        boards = [b for b in f.boards.all() if b.can_access(user)]
        if boards or pode:
            folders.append({'folder': f, 'boards': boards, 'n': len(boards)})
    geral = [b for b in dept.boards.filter(folder__isnull=True) if b.can_access(user)]
    return render(request, 'kanban/departamento.html', {
        'dept': dept, 'folders': folders, 'geral_boards': geral, 'pode_gerenciar': pode,
    })


@login_required
def pasta(request, dept_pk, folder_pk):
    """Quadros dentro de uma pasta."""
    user = request.user
    folder = get_object_or_404(
        BoardFolder.objects.select_related('department'), pk=folder_pk, department_id=dept_pk
    )
    dept = folder.department
    if not _pode_ver_departamento(user, dept):
        return HttpResponseForbidden()
    boards = [b for b in folder.boards.select_related('department').all() if b.can_access(user)]
    pode = pode_gerenciar_pastas(user, dept)
    posts, posts_restantes = _mural_posts(folder.posts, request)
    return render(request, 'kanban/pasta.html', {
        'dept': dept, 'folder': folder, 'boards': boards,
        'pode_gerenciar': pode,
        # Documentos + Mural (escopo pasta)
        'scope': 'pasta', 'owner_pk': folder.pk,
        'documentos': _paginar_documentos(folder.documentos, request),
        'posts': posts, 'posts_restantes': posts_restantes,
        'pode_escrever': True,        # pasta sempre editável
        'pode_gerenciar_conteudo': pode,
        'tab_inicial': request.GET.get('tab', 'quadros'),
    })


@login_required
def folder_create(request, dept_pk):
    dept = get_object_or_404(Department, pk=dept_pk)
    if not pode_gerenciar_pastas(request.user, dept):
        return HttpResponseForbidden()
    form = BoardFolderForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        folder = form.save(commit=False)
        folder.department = dept
        folder.created_by = request.user
        folder.save()
        messages.success(request, f'Pasta "{folder.name}" criada.')
        return redirect('kanban:departamento', dept_pk=dept.pk)
    return render(request, 'kanban/folder_form.html', {
        'form': form, 'dept': dept, 'title': 'Nova Pasta',
    })


@login_required
def folder_edit(request, pk):
    folder = get_object_or_404(BoardFolder.objects.select_related('department'), pk=pk)
    if not pode_gerenciar_pastas(request.user, folder.department):
        return HttpResponseForbidden()
    form = BoardFolderForm(request.POST or None, instance=folder)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, f'Pasta "{folder.name}" atualizada.')
        return redirect('kanban:departamento', dept_pk=folder.department_id)
    return render(request, 'kanban/folder_form.html', {
        'form': form, 'dept': folder.department, 'folder': folder,
        'title': f'Editar pasta: {folder.name}',
    })


@login_required
@require_POST
def folder_delete(request, pk):
    folder = get_object_or_404(BoardFolder.objects.select_related('department'), pk=pk)
    if not pode_gerenciar_pastas(request.user, folder.department):
        return HttpResponseForbidden()
    dept_pk = folder.department_id
    name = folder.name
    folder.delete()  # on_delete=SET_NULL nos quadros: eles voltam para "Geral"
    messages.success(request, f'Pasta "{name}" excluída. Os quadros foram movidos para "Geral".')
    return redirect('kanban:departamento', dept_pk=dept_pk)


# ───────────────────────── Projetos (entre áreas, com ciclo de vida) ─────────────────────────

def _board_writable(request, board):
    """False (com aviso) se o quadro está finalizado/somente-leitura."""
    if board.is_locked:
        messages.error(request, 'Projeto finalizado: somente leitura.')
        return False
    return True


def _pode_finalizar_projeto(user, board):
    return user.is_admin_ti or board.created_by_id == user.pk


@login_required
def projetos(request):
    """Lista de projetos (quadros entre áreas), com abas Ativos / Finalizados."""
    user = request.user
    aba = request.GET.get('aba', 'ativos')
    status = Board.Status.FINALIZADO if aba == 'finalizados' else Board.Status.ATIVO
    qs = Board.objects.filter(is_cross_department=True, status=status).select_related(
        'created_by'
    ).prefetch_related('member_departments', 'members')
    projetos_list = [b for b in qs if b.can_access(user)]
    # Notificações não lidas por projeto (cards + mural, atribuídas a este usuário)
    for b in projetos_list:
        b.unread_count = Notification.objects.filter(
            user=user, is_read=False, link__startswith=f'/kanban/{b.pk}/',
        ).count()
    return render(request, 'kanban/projetos.html', {
        'projetos': projetos_list,
        'aba': aba,
        'pode_criar': user.can_see_all or Department.objects.filter(leaders=user).exists(),
    })


@login_required
def projeto_create(request):
    user = request.user
    if not (user.can_see_all or Department.objects.filter(leaders=user).exists()):
        return HttpResponseForbidden()
    form = ProjectForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        board = form.save(commit=False)
        board.is_cross_department = True
        board.created_by = user
        board.status = Board.Status.ATIVO
        board.save()
        form.save_m2m()
        Column.objects.bulk_create([
            Column(board=board, name='A Fazer',      order=0, color='#64748b', column_type=Column.ColumnType.A_FAZER),
            Column(board=board, name='Em Andamento', order=1, color='#3b82f6', column_type=Column.ColumnType.EM_ANDAMENTO),
            Column(board=board, name='Status Final', order=2, color='#22c55e', column_type=Column.ColumnType.STATUS_FINAL),
        ])
        # Notifica participantes (pessoas avulsas + membros das áreas)
        destinatarios = set(board.members.all())
        for dept in board.member_departments.all():
            destinatarios.update(dept.users.filter(is_active=True))
        link = f'/kanban/{board.pk}/'
        for u in destinatarios:
            Notification.send(
                u, user, Notification.Type.PROJETO_NOVO,
                f'Novo projeto: {board.name}', 'Você foi incluído em um projeto entre áreas.', link,
            )
        messages.success(request, f'Projeto "{board.name}" criado.')
        return redirect('kanban:board_detail', pk=board.pk)
    return render(request, 'kanban/projeto_form.html', {'form': form, 'title': 'Novo Projeto'})


@login_required
@require_POST
def projeto_finalizar(request, pk):
    board = get_object_or_404(Board, pk=pk, is_cross_department=True)
    if not _pode_finalizar_projeto(request.user, board):
        return HttpResponseForbidden()
    if board.status != Board.Status.FINALIZADO:
        board.status = Board.Status.FINALIZADO
        board.finished_at = timezone.now()
        board.finished_by = request.user
        board.save(update_fields=['status', 'finished_at', 'finished_by'])
        destinatarios = set(board.members.all())
        for dept in board.member_departments.all():
            destinatarios.update(dept.users.filter(is_active=True))
        link = f'/kanban/{board.pk}/'
        for u in destinatarios:
            Notification.send(
                u, request.user, Notification.Type.PROJETO_FIM,
                f'Projeto finalizado: {board.name}', 'O projeto foi encerrado (somente leitura).', link,
            )
        messages.success(request, f'Projeto "{board.name}" finalizado.')
    return redirect('kanban:board_detail', pk=board.pk)


@login_required
@require_POST
def projeto_reabrir(request, pk):
    board = get_object_or_404(Board, pk=pk, is_cross_department=True)
    if not _pode_finalizar_projeto(request.user, board):
        return HttpResponseForbidden()
    if board.status != Board.Status.ATIVO:
        board.status = Board.Status.ATIVO
        board.finished_at = None
        board.finished_by = None
        board.save(update_fields=['status', 'finished_at', 'finished_by'])
        messages.success(request, f'Projeto "{board.name}" reaberto.')
    return redirect('kanban:board_detail', pk=board.pk)


# ───────────────────────── Documentos e Mural (pasta OU projeto) ─────────────────────────

def _scope_target(scope, obj_pk):
    if scope == 'pasta':
        return get_object_or_404(BoardFolder.objects.select_related('department'), pk=obj_pk)
    if scope == 'projeto':
        return get_object_or_404(Board, pk=obj_pk)
    from django.http import Http404
    raise Http404('Escopo inválido.')


def _scope_can_view(user, scope, owner):
    if scope == 'pasta':
        return _pode_ver_departamento(user, owner.department)
    return owner.can_access(user)  # projeto


def _scope_can_write(user, scope, owner):
    """Pode anexar documento / postar no mural."""
    if not _scope_can_view(user, scope, owner):
        return False
    if scope == 'projeto' and owner.is_locked:
        return False  # projeto finalizado = somente leitura
    return True


def _scope_can_manage(user, scope, owner):
    if scope == 'pasta':
        return pode_gerenciar_pastas(user, owner.department)
    return user.is_admin_ti or owner.created_by_id == user.pk  # projeto


def _scope_back_url(scope, owner, tab):
    if scope == 'pasta':
        url = reverse('kanban:pasta', kwargs={'dept_pk': owner.department_id, 'folder_pk': owner.pk})
    else:
        url = reverse('kanban:board_detail', kwargs={'pk': owner.pk})
    return f'{url}?tab={tab}'


def _scope_fk(scope, owner):
    return {'folder': owner} if scope == 'pasta' else {'board': owner}


MURAL_LIMIT = 50  # quantas mensagens recentes do mural carregar de início


def _mural_posts(manager, request):
    """Retorna (posts_ascendente, qtd_anteriores_ocultas) para o mural.
    Por padrão traz só as últimas MURAL_LIMIT; ?mural_all=1 traz todas."""
    qs = manager.select_related('author')
    if request.GET.get('mural_all') == '1':
        return list(qs.order_by('created_at')), 0
    total = manager.count()
    recentes = list(qs.order_by('-created_at')[:MURAL_LIMIT])[::-1]
    return recentes, max(0, total - len(recentes))


DOCS_POR_PAGINA = 20


def _paginar_documentos(manager, request):
    """Página de documentos (mais recentes primeiro). Usa ?doc_page= para não
    colidir com outros paginadores/estado de aba na mesma tela."""
    from django.core.paginator import Paginator
    qs = manager.select_related('enviado_por').order_by('-created_at')
    return Paginator(qs, DOCS_POR_PAGINA).get_page(request.GET.get('doc_page', 1))


@login_required
@require_POST
def documento_upload(request, scope, obj_pk):
    owner = _scope_target(scope, obj_pk)
    if not _scope_can_write(request.user, scope, owner):
        return HttpResponseForbidden()
    back = _scope_back_url(scope, owner, 'documentos')
    arquivo = request.FILES.get('arquivo')
    if not arquivo:
        messages.error(request, 'Selecione um arquivo.')
        return redirect(back)
    try:
        validate_file_extension(arquivo)
        validate_file_size(arquivo)
    except ValidationError as e:
        messages.error(request, e.message)
        return redirect(back)
    PastaDocumento.objects.create(
        arquivo=arquivo, nome_original=arquivo.name,
        descricao=(request.POST.get('descricao') or '').strip(),
        enviado_por=request.user, **_scope_fk(scope, owner),
    )
    messages.success(request, 'Documento anexado.')
    return redirect(back)


@login_required
@require_POST
def documento_delete(request, pk):
    doc = get_object_or_404(PastaDocumento.objects.select_related('folder__department', 'board'), pk=pk)
    scope, owner = ('pasta', doc.folder) if doc.folder_id else ('projeto', doc.board)
    if scope == 'projeto' and owner.is_locked:
        return HttpResponseForbidden()
    if not (doc.enviado_por_id == request.user.pk or _scope_can_manage(request.user, scope, owner)):
        return HttpResponseForbidden()
    doc.delete()
    messages.success(request, 'Documento excluído.')
    return redirect(_scope_back_url(scope, owner, 'documentos'))


@login_required
@require_POST
def post_create(request, scope, obj_pk):
    owner = _scope_target(scope, obj_pk)
    if not _scope_can_write(request.user, scope, owner):
        return HttpResponseForbidden()
    back = _scope_back_url(scope, owner, 'mural')
    content = (request.POST.get('content') or '').strip()
    if not content:
        messages.error(request, 'Escreva uma mensagem.')
        return redirect(back)
    PastaPost.objects.create(author=request.user, content=content, **_scope_fk(scope, owner))
    if scope == 'projeto':
        destinatarios = set(owner.members.all())
        for dept in owner.member_departments.all():
            destinatarios.update(dept.users.filter(is_active=True))
        link = f'/kanban/{owner.pk}/?tab=mural'
        trecho = content[:100] + ('…' if len(content) > 100 else '')
        for u in destinatarios:
            Notification.send(
                u, request.user, Notification.Type.PROJETO_MURAL,
                f'Nova mensagem no mural: {owner.name}', trecho, link,
            )
    return redirect(back)


@login_required
@require_POST
def post_delete(request, pk):
    post = get_object_or_404(PastaPost.objects.select_related('folder__department', 'board'), pk=pk)
    scope, owner = ('pasta', post.folder) if post.folder_id else ('projeto', post.board)
    if scope == 'projeto' and owner.is_locked:
        return HttpResponseForbidden()
    if not (post.author_id == request.user.pk or _scope_can_manage(request.user, scope, owner)):
        return HttpResponseForbidden()
    post.delete()
    messages.success(request, 'Mensagem excluída.')
    return redirect(_scope_back_url(scope, owner, 'mural'))


def _annotated_cards_qs(user):
    """Queryset base de cards com contagens + relações para o board, já filtrado
    pela visibilidade do usuário (esconde cards privados de quem não tem acesso)."""
    return Card.objects.visible_to(user).annotate(
        comment_count=Count('comments', distinct=True),
        subtask_total=Count('subtasks', distinct=True),
        subtask_done=Count('subtasks', filter=Q(subtasks__is_done=True), distinct=True),
    ).select_related('assignee', 'creator', 'source_subtask__card__column')


def _apply_card_filters(qs, request, today):
    """Aplica os filtros de prioridade/responsável/prazo vindos do #board-filters."""
    from datetime import timedelta
    priority = request.GET.get('priority')
    assignee_id = request.GET.get('assignee')
    prazo = request.GET.get('prazo')
    if priority:
        qs = qs.filter(priority=priority)
    if assignee_id:
        qs = qs.filter(assignee_id=assignee_id)
    if prazo == 'vencidos':
        qs = qs.filter(due_date__lt=today, final_status='')
    elif prazo == 'hoje':
        qs = qs.filter(due_date=today)
    elif prazo == 'semana':
        qs = qs.filter(due_date__gte=today, due_date__lte=today + timedelta(days=7))
    return qs


@login_required
def board_detail(request, pk):
    board = get_object_or_404(Board, pk=pk)
    if not board.can_access(request.user):
        return HttpResponseForbidden()
    sort_by = request.GET.get('sort', '')
    columns = build_grouped_columns(
        board.columns.prefetch_related(
            Prefetch('cards', queryset=_annotated_cards_qs(request.user))
        ),
        sort_by=sort_by,
    )
    board_members = CustomUser.objects.filter(
        assigned_cards__column__board=board, is_active=True
    ).distinct().order_by('first_name')
    back_url, back_label = _board_back(board)
    ctx = {
        'board': board,
        'columns': columns,
        'board_members': board_members,
        'pode_finalizar': _pode_finalizar_projeto(request.user, board),
        'back_url': back_url,
        'back_label': back_label,
    }
    if board.is_cross_department:
        # Marca como lidas as notificações relativas a este projeto (badges limpam ao abrir)
        Notification.objects.filter(
            user=request.user, is_read=False, link__startswith=f'/kanban/{board.pk}/',
        ).update(is_read=True)
        posts, posts_restantes = _mural_posts(board.posts, request)
        ctx.update({
            'scope': 'projeto', 'owner_pk': board.pk,
            'documentos': _paginar_documentos(board.documentos, request),
            'posts': posts, 'posts_restantes': posts_restantes,
            'pode_escrever': not board.is_locked,
            'pode_gerenciar_conteudo': request.user.is_admin_ti or board.created_by_id == request.user.pk,
            'tab_inicial': request.GET.get('tab', 'quadro'),
        })
    return render(request, 'kanban/board.html', ctx)


def _depts_gerenciaveis(user):
    """Departamentos onde o usuário pode criar quadros/pastas.

    Mesma regra de pode_gerenciar_pastas: admin TI e presidência gerenciam todos;
    os demais, apenas os departamentos que lideram. (can_see_all é permissão de
    LEITURA — inclui líder/diretor — e não deve liberar criação em qualquer área.)
    """
    if user.is_admin_ti or user.is_presidente:
        return Department.objects.all()
    return Department.objects.filter(leaders=user).distinct()


def _origem_back(request):
    """URL/rótulo de 'voltar' de acordo com a origem (departamento/pasta) da tela."""
    dept_pk = request.GET.get('department')
    folder_pk = request.GET.get('folder')
    if dept_pk and folder_pk:
        return reverse('kanban:pasta', kwargs={'dept_pk': dept_pk, 'folder_pk': folder_pk}), 'Voltar à pasta'
    if dept_pk:
        return reverse('kanban:departamento', kwargs={'dept_pk': dept_pk}), 'Voltar ao departamento'
    return reverse('kanban:departamentos'), 'Kanban'


def _board_back(board):
    """URL/rótulo de 'voltar' a partir de um quadro, respeitando de onde ele vive."""
    if board.is_cross_department:
        return reverse('kanban:projetos'), 'Projetos'
    if board.department_id and board.folder_id:
        return reverse('kanban:pasta', kwargs={'dept_pk': board.department_id, 'folder_pk': board.folder_id}), board.folder.name
    if board.department_id:
        return reverse('kanban:departamento', kwargs={'dept_pk': board.department_id}), board.department.name
    return reverse('kanban:departamentos'), 'Kanban'


@login_required
def board_create(request):
    user = request.user
    gerenciaveis = _depts_gerenciaveis(user)
    if not gerenciaveis.exists():
        return HttpResponseForbidden()
    initial = {}
    if request.GET.get('department'):
        initial['department'] = request.GET.get('department')
    if request.GET.get('folder'):
        initial['folder'] = request.GET.get('folder')
    form = BoardForm(request.POST or None, user=user, initial=initial or None)
    back_url, back_label = _origem_back(request)
    if request.method == 'POST' and form.is_valid():
        board = form.save(commit=False)
        # Só cria quadro em departamento que o usuário gerencia.
        if not board.department_id or not gerenciaveis.filter(pk=board.department_id).exists():
            return HttpResponseForbidden()
        board.created_by = user
        board.save()
        form.save_m2m()
        Column.objects.bulk_create([
            Column(board=board, name='A Fazer',      order=0, color='#64748b', column_type=Column.ColumnType.A_FAZER),
            Column(board=board, name='Em Andamento', order=1, color='#3b82f6', column_type=Column.ColumnType.EM_ANDAMENTO),
            Column(board=board, name='Status Final', order=2, color='#22c55e', column_type=Column.ColumnType.STATUS_FINAL),
        ])
        messages.success(request, f'Quadro "{board.name}" criado.')
        return redirect('kanban:board_detail', pk=board.pk)
    return render(request, 'kanban/board_form.html', {
        'form': form, 'title': 'Novo Quadro',
        'back_url': back_url, 'back_label': back_label,
    })


@login_required
def card_detail(request, board_pk, pk):
    board = get_object_or_404(Board, pk=board_pk)
    is_member = board.can_access(request.user)
    card = get_object_or_404(
        Card.objects.select_related('source_subtask__card__column__board'),
        pk=pk, column__board=board,
    )
    is_creator = card.creator_id == request.user.pk
    if not is_member and not is_creator:
        return HttpResponseForbidden()
    if not card.can_view(request.user):
        return HttpResponseForbidden()

    comment_form = CardCommentForm()
    subtask_form = SubTaskForm()

    if request.method == 'POST':
        if not is_member:
            return HttpResponseForbidden()
        if not _board_writable(request, board):
            return redirect('kanban:card_detail', board_pk=board.pk, pk=card.pk)
        action = request.POST.get('action')
        if action == 'comment':
            comment_form = CardCommentForm(request.POST)
            if comment_form.is_valid():
                c = comment_form.save(commit=False)
                c.card = card
                c.author = request.user
                c.save()
                CardActivity.objects.create(card=card, user=request.user, action='Comentou no card')
                _notify_comment(c, request.user)
                return redirect('kanban:card_detail', board_pk=board.pk, pk=card.pk)
        elif action == 'final_status':
            from django.utils import timezone as tz
            new_status = request.POST.get('final_status', '')
            valid = [c[0] for c in Card._meta.get_field('final_status').choices]
            if new_status in valid or new_status == '':
                card.final_status = new_status
                card.final_notes = request.POST.get('final_notes', '')
                if new_status and card.completed_at is None:
                    card.completed_at = tz.now()
                card.save(update_fields=['final_status', 'final_notes', 'completed_at'])
                CardActivity.objects.create(
                    card=card, user=request.user,
                    action=f'Registrou status final: {card.get_final_status_display() or "—"}'
                )
                if new_status:
                    _propagar_conclusao_para_subtarefa(card, request.user)
                if new_status and card.creator_id and card.creator_id != request.user.pk:
                    status_label = card.get_final_status_display()
                    link = f'/kanban/{board.pk}/card/{card.pk}/'
                    Notification.send(
                        user=card.creator,
                        actor=request.user,
                        ntype=Notification.Type.CARD_MOVED,
                        title=f'Sua solicitação foi encerrada: {status_label}',
                        body=card.title,
                        link=link,
                    )
            return redirect('kanban:card_detail', board_pk=board.pk, pk=card.pk)
        elif action == 'subtask':
            subtask_form = SubTaskForm(request.POST)
            if subtask_form.is_valid():
                st = subtask_form.save(commit=False)
                st.card = card
                st.created_by = request.user
                st.save()
                CardActivity.objects.create(
                    card=card, user=request.user,
                    action=f'Adicionou sub-tarefa: {st.title}'
                )

                desc_subtask = f'Sub-tarefa de: {card.title}\nBoard: {board.name}'
                depts_notificados = set()
                dept_destino = st.target_department or (st.assignee.department if st.assignee else None)
                if dept_destino:
                    criar_card_automatico(
                        department=dept_destino,
                        title=st.title,
                        description=desc_subtask,
                        creator=request.user,
                        assignee=st.assignee,
                        tags='subtarefa',
                        subtask=st,
                    )

                try:
                    _notify_subtask(st, request.user)
                except Exception:
                    pass
                messages.success(request, f'Sub-tarefa "{st.title}" adicionada.')
                return redirect('kanban:card_detail', board_pk=board.pk, pk=card.pk)

    subtasks = card.subtasks.select_related('assignee', 'target_department').prefetch_related(
        'anexos__enviado_por',
        'kanban_cards__anexos__enviado_por',
        'kanban_cards__column__board__department',
        'kanban_cards__comments__author',
        'kanban_cards__activities__user',
    )
    done_count = subtasks.filter(is_done=True).count()
    card_anexos = card.anexos.select_related('enviado_por').all()
    is_status_final = card.column.column_type == Column.ColumnType.STATUS_FINAL
    final_status_choices = Card._meta.get_field('final_status').choices
    from django.utils import timezone as tz
    return render(request, 'kanban/card_detail.html', {
        'board': board,
        'card': card,
        'comment_form': comment_form,
        'subtask_form': subtask_form,
        'subtasks': subtasks,
        'done_count': done_count,
        'is_status_final': is_status_final,
        'final_status_choices': final_status_choices,
        'card_anexos': card_anexos,
        'today': tz.now().date(),
        'is_member': is_member,
    })


@login_required
@require_POST
def subtask_toggle(request, pk):
    st = get_object_or_404(SubTask, pk=pk)
    board = st.card.column.board
    if not board.can_access(request.user):
        return HttpResponseForbidden()
    if not _board_writable(request, board):
        return redirect('kanban:card_detail', board_pk=board.pk, pk=st.card.pk)
    st.is_done = not st.is_done
    st.save(update_fields=['is_done'])
    CardActivity.objects.create(
        card=st.card, user=request.user,
        action=f'{"Concluiu" if st.is_done else "Reabriu"} sub-tarefa: {st.title}'
    )
    for kanban_card in st.kanban_cards.select_related('column__board').all():
        if st.is_done:
            mover_card_para_ultima_coluna(kanban_card)
        else:
            mover_card_para_primeira_coluna(kanban_card)
    return redirect('kanban:card_detail', board_pk=board.pk, pk=st.card.pk)


@login_required
@require_POST
def subtask_delete(request, pk):
    st = get_object_or_404(SubTask, pk=pk)
    board = st.card.column.board
    if not board.can_access(request.user):
        return HttpResponseForbidden()
    if not _board_writable(request, board):
        return redirect('kanban:card_detail', board_pk=board.pk, pk=st.card.pk)
    card_pk = st.card.pk
    st.delete()
    return redirect('kanban:card_detail', board_pk=board.pk, pk=card_pk)


@login_required
@require_POST
def subtask_attach(request, pk):
    st = get_object_or_404(SubTask, pk=pk)
    board = st.card.column.board
    if not board.can_access(request.user):
        return HttpResponseForbidden()
    if not _board_writable(request, board):
        return redirect('kanban:card_detail', board_pk=board.pk, pk=st.card.pk)
    arquivo = request.FILES.get('arquivo')
    if arquivo:
        try:
            validate_file_extension(arquivo)
            validate_file_size(arquivo)
        except ValidationError as e:
            messages.error(request, e.message)
            return redirect('kanban:card_detail', board_pk=board.pk, pk=st.card.pk)
        SubTaskAnexo.objects.create(
            subtask=st,
            arquivo=arquivo,
            nome_original=arquivo.name,
            enviado_por=request.user,
        )
        CardActivity.objects.create(
            card=st.card, user=request.user,
            action=f'Anexou documento na sub-tarefa: {st.title}'
        )
    return redirect('kanban:card_detail', board_pk=board.pk, pk=st.card.pk)


@login_required
@require_POST
def card_attach(request, board_pk, pk):
    board = get_object_or_404(Board, pk=board_pk)
    if not board.can_access(request.user):
        return HttpResponseForbidden()
    if not _board_writable(request, board):
        return redirect('kanban:board_detail', pk=board.pk)
    card = get_object_or_404(Card, pk=pk, column__board=board)
    if not card.can_view(request.user):
        return HttpResponseForbidden()
    arquivo = request.FILES.get('arquivo')
    if arquivo:
        try:
            validate_file_extension(arquivo)
            validate_file_size(arquivo)
        except ValidationError as e:
            messages.error(request, e.message)
            return redirect('kanban:card_detail', board_pk=board.pk, pk=card.pk)
        CardAnexo.objects.create(
            card=card,
            arquivo=arquivo,
            nome_original=arquivo.name,
            enviado_por=request.user,
        )
        CardActivity.objects.create(
            card=card, user=request.user,
            action=f'Anexou documento: {arquivo.name}'
        )
    return redirect('kanban:card_detail', board_pk=board.pk, pk=card.pk)


@login_required
def card_create(request, board_pk):
    board = get_object_or_404(Board, pk=board_pk)
    if not board.can_access(request.user):
        return HttpResponseForbidden()
    if not _board_writable(request, board):
        return redirect('kanban:board_detail', pk=board.pk)
    form = CardForm(request.POST or None, board=board)
    if request.method == 'POST' and form.is_valid():
        card = form.save(commit=False)
        card.creator = request.user
        last = Card.objects.filter(column=card.column).order_by('-order').first()
        card.order = (last.order + 1) if last else 0
        card.save()
        form.save_m2m()  # allowed_users (card privado)
        CardActivity.objects.create(card=card, user=request.user, action='Criou o card')
        AuditLog.log(
            request.user, AuditLog.Action.CARD_CREATE,
            resource_type='Card', resource_id=card.pk,
            ip=AuditMiddleware.get_client_ip(request),
        )
        _notify_card(card, request.user, created=True)
        if request.headers.get('HX-Request'):
            columns = build_grouped_columns(
                board.columns.prefetch_related(
                    Prefetch('cards', queryset=_annotated_cards_qs(request.user))
                ),
            )
            return render(request, 'kanban/partials/board_columns.html', {'board': board, 'columns': columns})
        return redirect('kanban:board_detail', pk=board.pk)
    return render(request, 'kanban/card_form.html', {'form': form, 'board': board, 'title': 'Novo Card'})


@login_required
def card_edit(request, board_pk, pk):
    board = get_object_or_404(Board, pk=board_pk)
    if not board.can_access(request.user):
        return HttpResponseForbidden()
    if not _board_writable(request, board):
        return redirect('kanban:board_detail', pk=board.pk)
    card = get_object_or_404(Card, pk=pk, column__board=board)
    if not card.can_view(request.user):
        return HttpResponseForbidden()
    old_assignee = card.assignee
    form = CardForm(request.POST or None, instance=card, board=board)
    if request.method == 'POST' and form.is_valid():
        card = form.save()
        CardActivity.objects.create(card=card, user=request.user, action='Editou o card')
        AuditLog.log(
            request.user, AuditLog.Action.CARD_UPDATE,
            resource_type='Card', resource_id=card.pk,
            ip=AuditMiddleware.get_client_ip(request),
        )
        # Notify only if assignee changed
        if card.assignee and card.assignee != old_assignee:
            _notify_card(card, request.user, created=False)
        return redirect('kanban:card_detail', board_pk=board.pk, pk=card.pk)
    return render(request, 'kanban/card_form.html', {
        'form': form, 'board': board, 'card': card, 'title': f'Editar: {card.title}'
    })


@login_required
@require_POST
def card_move(request, pk):
    card = get_object_or_404(Card, pk=pk)
    board = card.column.board
    if not board.can_access(request.user):
        return HttpResponseForbidden()
    if not card.can_view(request.user):
        return HttpResponseForbidden()
    if board.is_locked:
        return JsonResponse({'status': 'locked', 'detail': 'Projeto finalizado: somente leitura.'}, status=403)

    data = json.loads(request.body)
    column_id = data.get('column_id')
    order = data.get('order', 0)
    col = get_object_or_404(Column, pk=column_id, board=board)
    old_col = card.column
    card.column = col
    card.order = order
    card.save(update_fields=['column', 'order'])

    if old_col != col and col.column_type == Column.ColumnType.STATUS_FINAL:
        _propagar_conclusao_para_subtarefa(card, request.user)

    if old_col != col:
        CardActivity.objects.create(
            card=card, user=request.user,
            action=f'Moveu de "{old_col.name}" para "{col.name}"',
        )
        AuditLog.log(
            request.user, AuditLog.Action.CARD_UPDATE,
            resource_type='Card', resource_id=card.pk,
            ip=AuditMiddleware.get_client_ip(request),
        )
        card.refresh_from_db(fields=['assignee', 'creator'])
        notified = set()
        if card.assignee_id and card.assignee_id != request.user.pk:
            Notification.send(
                user=card.assignee,
                actor=request.user,
                ntype=Notification.Type.CARD_MOVED,
                title=f'Card movido para "{col.name}"',
                body=card.title,
                link=f'/kanban/{board.pk}/card/{card.pk}/',
            )
            notified.add(card.assignee_id)
        if card.creator_id and card.creator_id != request.user.pk and card.creator_id not in notified:
            Notification.send(
                user=card.creator,
                actor=request.user,
                ntype=Notification.Type.CARD_MOVED,
                title=f'Sua solicitação foi movida para "{col.name}"',
                body=card.title,
                link=f'/kanban/{board.pk}/card/{card.pk}/',
            )
    return JsonResponse({'status': 'ok'})


@login_required
@require_POST
def card_move_direction(request, pk):
    card = get_object_or_404(Card, pk=pk)
    board = card.column.board
    if not board.can_access(request.user):
        return HttpResponseForbidden()
    if not card.can_view(request.user):
        return HttpResponseForbidden()
    if not _board_writable(request, board):
        return redirect('kanban:board_detail', pk=board.pk)

    direction = request.POST.get('direction')
    columns = list(board.columns.order_by('order'))
    current_idx = next((i for i, c in enumerate(columns) if c.pk == card.column_id), None)

    redirect_to = request.POST.get('redirect_to')

    def _redirect():
        if redirect_to == 'meu_kanban':
            return redirect('kanban:meu_kanban')
        return redirect('kanban:board_detail', pk=board.pk)

    if current_idx is None:
        return _redirect()

    if direction == 'prev' and current_idx > 0:
        target_col = columns[current_idx - 1]
    elif direction == 'next' and current_idx < len(columns) - 1:
        target_col = columns[current_idx + 1]
    else:
        return _redirect()

    old_col = card.column
    card.column = target_col
    card.order = 0
    save_fields = ['column', 'order']
    # Ao sair de uma coluna de status final, limpa o desfecho para reeditar
    if old_col.column_type == Column.ColumnType.STATUS_FINAL and target_col.column_type != Column.ColumnType.STATUS_FINAL:
        card.final_status = ''
        card.final_notes = ''
        card.completed_at = None
        save_fields += ['final_status', 'final_notes', 'completed_at']
    card.save(update_fields=save_fields)
    if target_col.column_type == Column.ColumnType.STATUS_FINAL:
        _propagar_conclusao_para_subtarefa(card, request.user)
    CardActivity.objects.create(
        card=card, user=request.user,
        action=f'Moveu de "{old_col.name}" para "{target_col.name}"',
    )
    AuditLog.log(
        request.user, AuditLog.Action.CARD_UPDATE,
        resource_type='Card', resource_id=card.pk,
        ip=AuditMiddleware.get_client_ip(request),
    )
    card.refresh_from_db(fields=['assignee', 'creator'])
    notified = set()
    if card.assignee_id and card.assignee_id != request.user.pk:
        Notification.send(
            user=card.assignee,
            actor=request.user,
            ntype=Notification.Type.CARD_MOVED,
            title=f'Card movido para "{target_col.name}"',
            body=card.title,
            link=f'/kanban/{board.pk}/card/{card.pk}/',
        )
        notified.add(card.assignee_id)
    if card.creator_id and card.creator_id != request.user.pk and card.creator_id not in notified:
        Notification.send(
            user=card.creator,
            actor=request.user,
            ntype=Notification.Type.CARD_MOVED,
            title=f'Sua solicitação foi movida para "{target_col.name}"',
            body=card.title,
            link=f'/kanban/{board.pk}/card/{card.pk}/',
        )
    return _redirect()


@login_required
def board_columns_partial(request, pk):
    board = get_object_or_404(Board, pk=pk)
    if not board.can_access(request.user):
        return HttpResponseForbidden()

    from django.utils import timezone as tz
    today = tz.now().date()

    annotated_cards = _apply_card_filters(_annotated_cards_qs(request.user), request, today)
    sort_by = request.GET.get('sort', '')

    columns = build_grouped_columns(
        board.columns.prefetch_related(
            Prefetch('cards', queryset=annotated_cards)
        ),
        sort_by=sort_by,
    )
    return render(request, 'kanban/partials/board_columns.html', {
        'board': board,
        'columns': columns,
    })


@login_required
def board_finalizados(request, board_pk, column_pk):
    from django.core.paginator import Paginator
    from django.utils import timezone as tz
    from datetime import timedelta

    board = get_object_or_404(Board, pk=board_pk)
    if not board.can_access(request.user):
        return HttpResponseForbidden()
    col = get_object_or_404(Column, pk=column_pk, board=board,
                            column_type=Column.ColumnType.STATUS_FINAL)

    cards = col.cards.visible_to(request.user).select_related('assignee', 'creator').order_by('-updated_at')

    final_status = request.GET.get('final_status', '')
    if final_status:
        cards = cards.filter(final_status=final_status)

    periodo = request.GET.get('periodo', '')
    today = tz.now().date()
    if periodo == 'hoje':
        cards = cards.filter(completed_at__date=today)
    elif periodo == 'semana':
        cards = cards.filter(completed_at__date__gte=today - timedelta(days=7))
    elif periodo == 'mes':
        cards = cards.filter(completed_at__date__gte=today - timedelta(days=30))

    paginator = Paginator(cards, 20)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    return render(request, 'kanban/finalizados.html', {
        'board': board,
        'col': col,
        'page_obj': page_obj,
        'final_status': final_status,
        'periodo': periodo,
    })


@login_required
@require_POST
def card_delete(request, board_pk, pk):
    board = get_object_or_404(Board, pk=board_pk)
    card = get_object_or_404(Card, pk=pk, column__board=board)
    is_member = board.can_access(request.user)
    is_creator = card.creator_id == request.user.pk
    if not is_member and not is_creator:
        return HttpResponseForbidden()
    if not card.can_view(request.user):
        return HttpResponseForbidden()
    AuditLog.log(
        request.user, AuditLog.Action.CARD_DELETE,
        resource_type='Card', resource_id=card.pk,
        ip=AuditMiddleware.get_client_ip(request),
        title=card.title,
    )
    card.delete()
    messages.success(request, 'Solicitação excluída.' if is_creator and not is_member else 'Card excluído.')
    if is_creator and not is_member:
        return redirect('kanban:minhas_solicitacoes')
    return redirect('kanban:board_detail', pk=board.pk)


@login_required
def board_edit(request, pk):
    board = get_object_or_404(Board, pk=pk)
    # Projetos (entre áreas) não usam o formulário de quadro (que é por departamento).
    if board.is_cross_department:
        return redirect('kanban:board_detail', pk=board.pk)
    if not (request.user.is_admin_ti or (
        board.department and pode_gerenciar_pastas(request.user, board.department)
    )):
        return HttpResponseForbidden()
    form = BoardForm(request.POST or None, instance=board, user=request.user)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, f'Quadro "{board.name}" atualizado.')
        return redirect('kanban:board_detail', pk=board.pk)
    return render(request, 'kanban/board_form.html', {
        'form': form, 'board': board, 'title': f'Editar: {board.name}'
    })


@login_required
@require_POST
def board_delete(request, pk):
    if not request.user.is_admin_ti:
        return HttpResponseForbidden()
    board = get_object_or_404(Board, pk=pk)
    name = board.name
    dept_pk = board.department_id
    board.delete()
    messages.success(request, f'Quadro "{name}" excluído.')
    if dept_pk:
        return redirect('kanban:departamento', dept_pk=dept_pk)
    return redirect('kanban:departamentos')


@login_required
def column_create(request, board_pk):
    if not request.user.is_admin_ti:
        return HttpResponseForbidden()
    board = get_object_or_404(Board, pk=board_pk)
    if not _board_writable(request, board):
        return redirect('kanban:board_detail', pk=board.pk)
    form = ColumnForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        col = form.save(commit=False)
        col.board = board
        last = board.columns.order_by('-order').first()
        col.order = (last.order + 1) if last else 0
        col.save()
        messages.success(request, f'Coluna "{col.name}" criada.')
        return redirect('kanban:board_detail', pk=board.pk)
    return render(request, 'kanban/column_form.html', {
        'form': form, 'board': board, 'title': 'Nova Coluna'
    })


@login_required
def column_edit(request, board_pk, pk):
    if not request.user.is_admin_ti:
        return HttpResponseForbidden()
    board = get_object_or_404(Board, pk=board_pk)
    if not _board_writable(request, board):
        return redirect('kanban:board_detail', pk=board.pk)
    column = get_object_or_404(Column, pk=pk, board=board)
    form = ColumnForm(request.POST or None, instance=column)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, f'Coluna "{column.name}" atualizada.')
        return redirect('kanban:board_detail', pk=board.pk)
    return render(request, 'kanban/column_form.html', {
        'form': form, 'board': board, 'column': column, 'title': f'Editar coluna: {column.name}'
    })


@login_required
@require_POST
def column_delete(request, board_pk, pk):
    if not request.user.is_admin_ti:
        return HttpResponseForbidden()
    board = get_object_or_404(Board, pk=board_pk)
    if not _board_writable(request, board):
        return redirect('kanban:board_detail', pk=board.pk)
    column = get_object_or_404(Column, pk=pk, board=board)
    if column.cards.exists():
        messages.error(request, f'A coluna "{column.name}" possui cards. Mova ou exclua os cards antes.')
        return redirect('kanban:board_detail', pk=board.pk)
    name = column.name
    column.delete()
    messages.success(request, f'Coluna "{name}" excluída.')
    return redirect('kanban:board_detail', pk=board.pk)


@login_required
def board_access(request, pk):
    """Gerencia quem tem acesso de exceção a um board (apenas ADMIN_TI)."""
    if not request.user.can_manage_users:
        return HttpResponseForbidden()
    board = get_object_or_404(Board, pk=pk)

    if request.method == 'POST':
        action = request.POST.get('action')
        user_id = request.POST.get('user_id')
        if user_id:
            from core.models import CustomUser as CU
            target = get_object_or_404(CU, pk=user_id)
            if action == 'add':
                board.members.add(target)
                messages.success(request, f'{target.get_full_name() or target.email} pode acessar "{board.name}".')
            elif action == 'remove':
                board.members.remove(target)
                messages.success(request, f'Acesso de {target.get_full_name() or target.email} removido.')
        return redirect('kanban:board_access', pk=pk)

    from core.models import CustomUser as CU, Department
    current_members = board.members.prefetch_related('departments').order_by('first_name')
    dept_users = CU.objects.filter(
        is_active=True, is_approved=True
    ).exclude(
        pk__in=board.members.values('pk')
    ).prefetch_related('departments').order_by('first_name')
    return render(request, 'kanban/board_access.html', {
        'board': board,
        'current_members': current_members,
        'dept_users': dept_users,
    })


@login_required
def analise(request):
    if not request.user.can_see_all:
        return HttpResponseForbidden()

    from django.utils import timezone
    from django.db.models import F as DbF, Avg
    from django.db.models.functions import TruncDate
    from datetime import timedelta
    from collections import Counter
    from core.models import Department

    today = timezone.now().date()
    CT = Column.ColumnType

    periodo = request.GET.get('periodo', '30d')
    if periodo == '7d':
        desde = today - timedelta(days=6)
    elif periodo == '90d':
        desde = today - timedelta(days=89)
    else:
        desde = today - timedelta(days=29)
        periodo = '30d'

    lider_depts = request.user.departments.all() if request.user.is_lider else None

    all_cards = Card.objects.visible_to(request.user).select_related('column__board__department', 'assignee')
    if lider_depts is not None:
        all_cards = all_cards.filter(column__board__department__in=lider_depts)

    # ── Snapshot atual ──────────────────────────────────────────────────────────
    total     = all_cards.count()
    a_fazer   = all_cards.filter(column__column_type=CT.A_FAZER).count()
    em_andamento = all_cards.filter(column__column_type=CT.EM_ANDAMENTO).count()
    status_final = all_cards.filter(column__column_type=CT.STATUS_FINAL).count()
    total_ativos = a_fazer + em_andamento

    ativas_com_prazo = all_cards.exclude(column__column_type=CT.STATUS_FINAL).filter(due_date__isnull=False)
    no_prazo = ativas_com_prazo.filter(due_date__gte=today).count()
    vencidos  = ativas_com_prazo.filter(due_date__lt=today, final_status='').count()

    stale_cutoff = today - timedelta(days=5)
    stale_count = all_cards.exclude(column__column_type=CT.STATUS_FINAL).filter(
        updated_at__date__lte=stale_cutoff
    ).count()

    # ── Finalizados no período ──────────────────────────────────────────────────
    fin_periodo = all_cards.filter(
        column__column_type=CT.STATUS_FINAL,
        completed_at__date__gte=desde,
    )
    throughput = fin_periodo.count()

    ct_list = list(fin_periodo.filter(completed_at__isnull=False).values_list('created_at', 'completed_at'))
    cycle_days = [(c - cr).days for cr, c in ct_list if c > cr]
    cycle_time_avg = round(sum(cycle_days) / len(cycle_days), 1) if cycle_days else None

    # ── Desfechos ───────────────────────────────────────────────────────────────
    concluidos    = all_cards.filter(final_status='concluido').count()
    nao_concluidos = all_cards.filter(final_status='nao_concluido').count()
    cancelados    = all_cards.filter(final_status='cancelado').count()
    concluidos_com_atraso = all_cards.filter(
        final_status__in=['concluido', 'nao_concluido', 'cancelado'],
        due_date__isnull=False, completed_at__isnull=False,
    ).filter(completed_at__date__gt=DbF('due_date')).count()

    # ── Throughput diário (chart) ────────────────────────────────────────────────
    n_days = (today - desde).days + 1
    date_range = [desde + timedelta(days=i) for i in range(n_days)]
    daily_raw = list(
        fin_periodo.annotate(dia=TruncDate('completed_at'))
        .values('dia').annotate(n=Count('id')).order_by('dia')
    )
    daily_map = {d['dia']: d['n'] for d in daily_raw}
    chart_labels     = json.dumps([d.strftime('%d/%m') for d in date_range])
    chart_throughput = json.dumps([daily_map.get(d, 0) for d in date_range])

    # ── Distribuição por prioridade (ativos) ────────────────────────────────────
    prio_qs  = all_cards.exclude(column__column_type=CT.STATUS_FINAL).values('priority').annotate(n=Count('id'))
    prio_map = {p['priority']: p['n'] for p in prio_qs}
    prioridades = [
        {'label': 'Urgente', 'key': 'URGENT', 'color': '#7c3aed', 'n': prio_map.get('URGENT', 0)},
        {'label': 'Alta',    'key': 'HIGH',   'color': '#ef4444', 'n': prio_map.get('HIGH', 0)},
        {'label': 'Média',   'key': 'MEDIUM', 'color': '#f59e0b', 'n': prio_map.get('MEDIUM', 0)},
        {'label': 'Baixa',   'key': 'LOW',    'color': '#22c55e', 'n': prio_map.get('LOW', 0)},
    ]

    # ── Por responsável ──────────────────────────────────────────────────────────
    resp_qs = (
        all_cards.filter(assignee__isnull=False)
        .values('assignee__id', 'assignee__first_name', 'assignee__last_name')
        .annotate(
            total=Count('id'),
            ativos=Count('id', filter=~Q(column__column_type=CT.STATUS_FINAL)),
            finalizados=Count('id', filter=Q(column__column_type=CT.STATUS_FINAL)),
            vencidos_r=Count('id', filter=Q(
                due_date__lt=today, due_date__isnull=False, final_status='',
            ) & ~Q(column__column_type=CT.STATUS_FINAL)),
        ).order_by('-total')[:15]
    )
    por_responsavel = [
        {
            'nome': f"{r['assignee__first_name']} {r['assignee__last_name']}".strip() or '—',
            'total': r['total'],
            'ativos': r['ativos'],
            'finalizados': r['finalizados'],
            'vencidos': r['vencidos_r'],
        }
        for r in resp_qs
    ]
    max_resp_total = max((r['total'] for r in por_responsavel), default=1)

    # ── Top tags ────────────────────────────────────────────────────────────────
    tags_counter = Counter()
    for tags_str in all_cards.exclude(tags='').values_list('tags', flat=True):
        for tag in tags_str.split(','):
            t = tag.strip().lower()
            if t:
                tags_counter[t] += 1
    top_tags = tags_counter.most_common(12)

    # ── Por departamento ─────────────────────────────────────────────────────────
    dept_stats = []
    depts_iter = (
        lider_depts.filter(boards__isnull=False).distinct().order_by('name')
        if lider_depts is not None
        else Department.objects.filter(boards__isnull=False).distinct().order_by('name')
    )
    for dept in depts_iter:
        dc = Card.objects.visible_to(request.user).filter(column__board__department=dept)
        dept_stats.append({
            'dept': dept,
            'total': dc.count(),
            'a_fazer': dc.filter(column__column_type=CT.A_FAZER).count(),
            'em_andamento': dc.filter(column__column_type=CT.EM_ANDAMENTO).count(),
            'status_final': dc.filter(column__column_type=CT.STATUS_FINAL).count(),
            'vencidos': dc.exclude(column__column_type=CT.STATUS_FINAL).filter(
                due_date__lt=today, due_date__isnull=False, final_status=''
            ).count(),
            'concluidos_com_atraso': dc.filter(
                final_status__in=['concluido', 'nao_concluido', 'cancelado'],
                due_date__isnull=False, completed_at__isnull=False,
            ).filter(completed_at__date__gt=DbF('due_date')).count(),
        })

    return render(request, 'kanban/analise.html', {
        'periodo': periodo,
        'desde': desde,
        'hoje': today,
        'total': total,
        'a_fazer': a_fazer,
        'em_andamento': em_andamento,
        'status_final': status_final,
        'total_ativos': total_ativos,
        'no_prazo': no_prazo,
        'vencidos': vencidos,
        'stale_count': stale_count,
        'throughput': throughput,
        'cycle_time_avg': cycle_time_avg,
        'concluidos': concluidos,
        'nao_concluidos': nao_concluidos,
        'cancelados': cancelados,
        'concluidos_com_atraso': concluidos_com_atraso,
        'dept_stats': dept_stats,
        'prioridades': prioridades,
        'por_responsavel': por_responsavel,
        'max_resp_total': max_resp_total,
        'top_tags': top_tags,
        'chart_labels': chart_labels,
        'chart_throughput': chart_throughput,
    })


_PRIORITY_LABEL = {
    'LOW':    'Baixa',
    'MEDIUM': 'Média',
    'HIGH':   'Alta',
    'URGENT': 'URGENTE',
}

_PRIORITY_PREFIX = {
    'LOW':    '',
    'MEDIUM': '',
    'HIGH':   '[ALTA] ',
    'URGENT': '[URGENTE] ',
}


def _card_body(card) -> str:
    """Monta corpo da notificação com prioridade e prazo."""
    from django.utils.timezone import now
    parts = [card.title]
    pri = card.priority
    if pri in ('HIGH', 'URGENT'):
        parts.append(f'Prioridade: {_PRIORITY_LABEL[pri]}')
    if card.due_date:
        today = now().date()
        delta = (card.due_date - today).days
        if delta < 0:
            parts.append(f'Prazo: VENCIDO há {abs(delta)} dia(s)')
        elif delta == 0:
            parts.append('Prazo: HOJE')
        elif delta <= 3:
            parts.append(f'Prazo: em {delta} dia(s)')
        else:
            parts.append(f'Prazo: {card.due_date.strftime("%d/%m/%Y")}')
    return ' · '.join(parts)


def _propagar_conclusao_para_subtarefa(card, actor):
    subtask = card.source_subtask
    if not subtask or subtask.is_done:
        return
    subtask.is_done = True
    subtask.save(update_fields=['is_done'])
    parent_card = subtask.card
    CardActivity.objects.create(
        card=parent_card, user=actor,
        action=f'Sub-tarefa concluída automaticamente: {subtask.title}',
    )
    link = f'/kanban/{parent_card.column.board_id}/card/{parent_card.pk}/'
    notified = set()
    for recipient in (subtask.created_by, parent_card.creator):
        if recipient and recipient.pk not in notified:
            Notification.send(
                user=recipient, actor=actor,
                ntype=Notification.Type.CARD_MOVED,
                title=f'Sub-tarefa concluída: {subtask.title}',
                body=parent_card.title,
                link=link,
            )
            notified.add(recipient.pk)
    _propagar_conclusao_para_subtarefa(parent_card, actor)


def _notify_subtask(subtask, actor):
    card = subtask.card
    board = card.column.board
    link = f'/kanban/{board.pk}/card/{card.pk}/'
    prefix = _PRIORITY_PREFIX.get(card.priority, '')

    if subtask.assignee and subtask.assignee != actor:
        Notification.send(
            user=subtask.assignee, actor=actor,
            ntype=Notification.Type.CARD_ASSIGNED,
            title=f'{prefix}Sub-tarefa atribuída a você em "{card.title}"',
            body=f'{subtask.title} · {_card_body(card)}',
            link=link,
        )

    if subtask.target_department:
        dept = subtask.target_department
        for member in CustomUser.objects.filter(department=dept, is_active=True, is_approved=True):
            if member != actor:
                Notification.send(
                    user=member, actor=actor,
                    ntype=Notification.Type.CARD_CROSS,
                    title=f'{prefix}Nova sub-tarefa para {dept.name}',
                    body=f'"{subtask.title}" em "{card.title}" · {_card_body(card)}',
                    link=link,
                )


def _notify_comment(comment, actor):
    card = comment.card
    board = card.column.board
    link = f'/kanban/{board.pk}/card/{card.pk}/'
    targets = set()
    if card.assignee and card.assignee != actor:
        targets.add(card.assignee)
    if card.creator and card.creator != actor:
        targets.add(card.creator)
    for user in targets:
        Notification.send(
            user=user, actor=actor,
            ntype=Notification.Type.CARD_COMMENT,
            title=f'{actor.get_full_name() or actor.email} comentou em "{card.title}"',
            body=comment.content[:120],
            link=link,
        )


def _notify_card(card, actor, created: bool):
    board = card.column.board
    link = f'/kanban/{board.pk}/card/{card.pk}/'
    verb = 'criou' if created else 'atualizou'
    prefix = _PRIORITY_PREFIX.get(card.priority, '')

    targets = set()

    # Notifica o responsável direto
    if card.assignee and card.assignee != actor:
        Notification.send(
            user=card.assignee,
            actor=actor,
            ntype=Notification.Type.CARD_ASSIGNED,
            title=f'{prefix}{actor.get_full_name() or actor.email} {verb} um card para você',
            body=_card_body(card),
            link=link,
        )
        targets.add(card.assignee)

    # Notifica líderes do departamento-alvo quando o card é cross-dept
    if board.department and not actor.departments.filter(pk=board.department_id).exists():
        dept = board.department
        for ldr in dept.leaders.all():
            if ldr != actor and ldr not in targets:
                Notification.send(
                    user=ldr,
                    actor=actor,
                    ntype=Notification.Type.CARD_CROSS,
                    title=f'{prefix}Card cross-departamento em {dept.name}',
                    body=f'{actor.get_full_name() or actor.email} {verb} "{card.title}" · {_card_body(card)}',
                    link=link,
                )

    # Se o board é do próprio departamento do ator mas sem responsável →
    # notifica os líderes do dept (para visibilidade)
    elif board.department and actor.departments.filter(pk=board.department_id).exists() and not card.assignee and created:
        dept = board.department
        for ldr in dept.leaders.all():
            if ldr != actor and ldr not in targets:
                Notification.send(
                    user=ldr,
                    actor=actor,
                    ntype=Notification.Type.CARD_DEPT,
                    title=f'{prefix}Novo card em {dept.name}',
                    body=_card_body(card),
                    link=link,
                )


_PRIORITY_ORDER = {'URGENT': 0, 'HIGH': 1, 'MEDIUM': 2, 'LOW': 3}


@login_required
def meu_kanban(request):
    cards = list(
        Card.objects
        .filter(assignee=request.user)
        .select_related('column__board__department', 'creator', 'source_subtask')
        .prefetch_related('subtasks')
    )
    cards.sort(key=lambda c: (_PRIORITY_ORDER.get(c.priority, 9), c.due_date or __import__('datetime').date(9999, 12, 31)))

    a_fazer     = [c for c in cards if c.column.column_type == Column.ColumnType.A_FAZER]
    em_andamento = [c for c in cards if c.column.column_type == Column.ColumnType.EM_ANDAMENTO]
    concluidos  = [c for c in cards if c.column.column_type == Column.ColumnType.STATUS_FINAL]

    return render(request, 'kanban/meu_kanban.html', {
        'a_fazer': a_fazer,
        'em_andamento': em_andamento,
        'concluidos': concluidos,
        'total_ativos': len(a_fazer) + len(em_andamento),
    })


@login_required
def solicitar_rapida(request):
    if request.method == 'POST':
        titulo = request.POST.get('titulo', '').strip()
        descricao = request.POST.get('descricao', '').strip()
        dept_id = request.POST.get('departamento')
        prioridade = request.POST.get('prioridade', 'MEDIUM')
        assignee_id = request.POST.get('assignee')
        tags_extra = request.POST.get('tags', '').strip()

        if titulo and dept_id:
            dept = get_object_or_404(Department, pk=dept_id)
            desc_completa = f'[Solicitação direta]\n\n{descricao}' if descricao else '[Solicitação direta]'
            tags_value = 'solicitacao'
            if tags_extra:
                tags_value = f'solicitacao,{tags_extra}'
            card = criar_card_automatico(
                department=dept,
                title=titulo,
                description=desc_completa,
                creator=request.user,
                tags=tags_value,
            )
            if card:
                update_fields = []
                if prioridade in ('LOW', 'MEDIUM', 'HIGH', 'URGENT'):
                    card.priority = prioridade
                    update_fields.append('priority')
                if assignee_id:
                    try:
                        card.assignee = CustomUser.objects.get(pk=assignee_id, is_active=True)
                        update_fields.append('assignee')
                    except CustomUser.DoesNotExist:
                        pass
                if tags_extra:
                    card.tags = tags_value
                    update_fields.append('tags')
                if update_fields:
                    card.save(update_fields=update_fields)
                for arquivo in request.FILES.getlist('arquivos'):
                    try:
                        validate_file_extension(arquivo)
                        validate_file_size(arquivo)
                        CardAnexo.objects.create(
                            card=card,
                            arquivo=arquivo,
                            nome_original=arquivo.name,
                            enviado_por=request.user,
                        )
                    except ValidationError:
                        pass
                _notify_card(card, request.user, created=True)
                AuditLog.log(
                    request.user, AuditLog.Action.CARD_CREATE,
                    resource_type='Card', resource_id=card.pk,
                    ip=AuditMiddleware.get_client_ip(request),
                    title=card.title,
                )
                messages.success(request, f'Solicitação enviada para {dept.name}!')
                return redirect('kanban:card_detail', board_pk=card.column.board.pk, pk=card.pk)
        messages.error(request, 'Preencha o título e o departamento.')

    departments = Department.objects.all().order_by('name')
    users = CustomUser.objects.filter(is_active=True, is_approved=True).prefetch_related('departments').order_by('first_name', 'last_name')
    return render(request, 'kanban/solicitar.html', {'departments': departments, 'users': users})


@login_required
def minhas_solicitacoes(request):
    filtro = request.GET.get('filtro', 'ativas')

    cards = (
        Card.objects
        .filter(creator=request.user, tags__contains='solicitacao')
        .select_related('column__board__department', 'assignee')
        .order_by('-created_at')
    )

    if filtro == 'finalizadas':
        cards = cards.filter(column__column_type=Column.ColumnType.STATUS_FINAL)
    else:
        cards = cards.exclude(column__column_type=Column.ColumnType.STATUS_FINAL)

    return render(request, 'kanban/minhas_solicitacoes.html', {
        'cards': cards,
        'filtro': filtro,
    })


@login_required
def tarefas_hub(request):
    """Hub de acompanhamento: caixas dos quadros/projetos acessíveis (com contagem
    de tarefas ativas). Clicar entra na tabela de tarefas daquele quadro."""
    from django.db.models import Count
    CT = Column.ColumnType
    boards = list(
        _accessible_boards(request.user)
        .select_related('department', 'created_by')
        .prefetch_related('member_departments')
        .order_by('name')
    )
    ids = [b.pk for b in boards]
    counts = dict(
        Card.objects.visible_to(request.user)
        .filter(column__board_id__in=ids)
        .exclude(column__column_type=CT.STATUS_FINAL)
        .order_by()  # limpa Meta.ordering p/ não vazar no GROUP BY
        .values_list('column__board_id')
        .annotate(n=Count('id', distinct=True))
    )
    for b in boards:
        b.task_count = counts.get(b.pk, 0)
    return render(request, 'kanban/tarefas_hub.html', {
        'dept_boards': [b for b in boards if not b.is_cross_department],
        'projetos':    [b for b in boards if b.is_cross_department],
        'total_tarefas': sum(counts.values()),
    })


@login_required
def todas_tarefas(request):
    """Visão global tipo tabela: todas as tarefas dos quadros que o usuário acessa,
    com Responsável, Data e Status (a coluna do card). Filtrável e paginada."""
    from django.core.paginator import Paginator
    from django.db.models import Case, When, IntegerField, F
    from django.utils import timezone as tz
    CT = Column.ColumnType
    today = tz.now().date()

    accessible_ids = list(_accessible_boards(request.user).values_list('pk', flat=True))
    cards = (
        Card.objects.visible_to(request.user)
        .filter(column__board_id__in=accessible_ids)
        .select_related('assignee', 'creator', 'column', 'column__board', 'column__board__department')
    )

    # ── Filtros ──────────────────────────────────────────────────────────────
    q = (request.GET.get('q') or '').strip()
    if q:
        cards = cards.filter(title__icontains=q)

    board_id = request.GET.get('board')
    if board_id:
        cards = cards.filter(column__board_id=board_id)

    status = request.GET.get('status', '')
    valid_status = {CT.A_FAZER, CT.EM_ANDAMENTO, CT.STATUS_FINAL}
    if status in valid_status:
        cards = cards.filter(column__column_type=status)
    elif status != 'todos':
        # padrão: esconde finalizados
        cards = cards.exclude(column__column_type=CT.STATUS_FINAL)

    # prioridade / responsável / prazo (reusa a mesma lógica do board)
    cards = _apply_card_filters(cards, request, today)

    # ── Ordenação ────────────────────────────────────────────────────────────
    sort = request.GET.get('sort', '')
    if sort == 'prazo':
        cards = cards.order_by(F('due_date').asc(nulls_last=True), '-updated_at')
    elif sort == 'prioridade':
        cards = cards.annotate(_prio=Case(
            When(priority='URGENT', then=0), When(priority='HIGH', then=1),
            When(priority='MEDIUM', then=2), When(priority='LOW', then=3),
            default=4, output_field=IntegerField(),
        )).order_by('_prio', F('due_date').asc(nulls_last=True))
    elif sort == 'titulo':
        cards = cards.order_by('title')
    elif sort == 'responsavel':
        cards = cards.order_by('assignee__first_name', 'assignee__last_name', '-updated_at')
    else:
        sort = 'atualizacao'
        cards = cards.order_by('-updated_at')

    paginator = Paginator(cards, 40)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    # ── Querystrings p/ links (preservam filtros) ────────────────────────────
    qs_nopage = request.GET.copy()
    qs_nopage.pop('page', None)
    qs_nosort = qs_nopage.copy()
    qs_nosort.pop('sort', None)

    # ── Opções dos dropdowns ─────────────────────────────────────────────────
    boards = _accessible_boards(request.user).order_by('name')
    sel_board = boards.filter(pk=board_id).first() if board_id else None
    responsaveis = (
        CustomUser.objects
        .filter(assigned_cards__column__board_id__in=accessible_ids, is_active=True)
        .distinct().order_by('first_name', 'last_name')
    )

    return render(request, 'kanban/todas_tarefas.html', {
        'page_obj': page_obj,
        'total': paginator.count,
        'boards': boards,
        'sel_board': sel_board,
        'responsaveis': responsaveis,
        'status_choices': CT.choices,
        'qs_nopage': qs_nopage.urlencode(),
        'qs_nosort': qs_nosort.urlencode(),
        # ecoar filtros p/ manter estado nos selects e na paginação
        'f': {
            'q': q, 'board': board_id or '', 'status': status,
            'assignee': request.GET.get('assignee', ''),
            'priority': request.GET.get('priority', ''),
            'prazo': request.GET.get('prazo', ''),
            'sort': sort,
        },
    })


# ── Tarefas Recorrentes ───────────────────────────────────────────────────────

def _accessible_boards(user):
    """Boards que o usuário pode ver — espelha Board.can_access()."""
    if user.can_see_all:
        return Board.objects.all()
    return Board.objects.filter(
        Q(is_global=True)
        | Q(members=user)
        | Q(department__in=user.departments.all())
        | Q(is_cross_department=True, member_departments__in=user.departments.all())
    ).distinct()


def _can_edit_recurring(user, task):
    """Criador da tarefa ou admin podem editar/excluir/pausar."""
    return task.created_by == user or user.can_see_all


@login_required
def recurring_list(request):
    accessible = _accessible_boards(request.user).values_list('pk', flat=True)
    tasks = (RecurringTask.objects
             .filter(board__in=accessible)
             .select_related('board', 'column', 'assignee', 'created_by')
             .order_by('board__name', 'title'))
    return render(request, 'kanban/recurring_list.html', {'tasks': tasks})


@login_required
def recurring_create(request):
    form = RecurringTaskForm(request.POST or None, user=request.user)
    if request.method == 'POST' and form.is_valid():
        task = form.save(commit=False)
        task.created_by = request.user
        task.save()
        messages.success(request, f'Tarefa recorrente "{task.title}" criada.')
        return redirect('kanban:recurring_list')
    return render(request, 'kanban/recurring_form.html', {
        'form': form, 'title': 'Nova Tarefa Recorrente',
    })


@login_required
def recurring_edit(request, pk):
    accessible = _accessible_boards(request.user).values_list('pk', flat=True)
    task = get_object_or_404(RecurringTask, pk=pk, board__in=accessible)
    if not _can_edit_recurring(request.user, task):
        return HttpResponseForbidden()
    form = RecurringTaskForm(request.POST or None, instance=task, user=request.user)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, f'Tarefa recorrente "{task.title}" atualizada.')
        return redirect('kanban:recurring_list')
    return render(request, 'kanban/recurring_form.html', {
        'form': form, 'title': f'Editar: {task.title}', 'task': task,
    })


@login_required
@require_POST
def recurring_toggle(request, pk):
    accessible = _accessible_boards(request.user).values_list('pk', flat=True)
    task = get_object_or_404(RecurringTask, pk=pk, board__in=accessible)
    if not _can_edit_recurring(request.user, task):
        return HttpResponseForbidden()
    task.active = not task.active
    task.save(update_fields=['active'])
    status = 'ativada' if task.active else 'pausada'
    messages.success(request, f'Tarefa "{task.title}" {status}.')
    return redirect('kanban:recurring_list')


@login_required
@require_POST
def recurring_delete(request, pk):
    accessible = _accessible_boards(request.user).values_list('pk', flat=True)
    task = get_object_or_404(RecurringTask, pk=pk, board__in=accessible)
    if not _can_edit_recurring(request.user, task):
        return HttpResponseForbidden()
    name = task.title
    task.delete()
    messages.success(request, f'Tarefa recorrente "{name}" excluída.')
    return redirect('kanban:recurring_list')


@login_required
@require_POST
def recurring_run_now(request, pk):
    """Gera o card manualmente, independente do agendamento."""
    accessible = _accessible_boards(request.user).values_list('pk', flat=True)
    task = get_object_or_404(RecurringTask, pk=pk, board__in=accessible)
    from django.utils.timezone import now
    card = task.generate_card(now().date())
    messages.success(request, f'Card "{card.title}" gerado no quadro {task.board.name}.')
    return redirect('kanban:recurring_list')


@login_required
def recurring_columns_api(request, board_pk):
    """Retorna as colunas de um board para o select dinâmico do formulário."""
    board = get_object_or_404(Board, pk=board_pk)
    if not board.can_access(request.user):
        return JsonResponse({'columns': []})
    cols = list(board.columns.values('id', 'name').order_by('order'))
    return JsonResponse({'columns': cols})
