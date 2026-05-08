import json
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.db.models import Prefetch
from django.http import JsonResponse, HttpResponseForbidden
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST

from core.models import AuditLog, Notification, CustomUser
from core.middleware import AuditMiddleware
from .models import Board, Column, Card, CardComment, CardActivity, SubTask
from .forms import BoardForm, ColumnForm, CardForm, CardCommentForm, SubTaskForm


@login_required
def board_list(request):
    user = request.user
    if user.can_see_all:
        boards = Board.objects.all().select_related('department', 'created_by')
    else:
        from django.db.models import Q
        boards = Board.objects.filter(
            Q(department=user.department) |
            Q(members=user) |
            Q(is_global=True)
        ).distinct().select_related('department', 'created_by')
    # Separate global board for easier template use
    global_board = boards.filter(is_global=True).first()
    dept_boards = boards.filter(is_global=False, is_cross_department=False, is_auto=True)
    manual_boards = boards.filter(is_global=False, is_auto=False)
    return render(request, 'kanban/list.html', {
        'boards': boards,
        'global_board': global_board,
        'dept_boards': dept_boards,
        'manual_boards': manual_boards,
    })


@login_required
def board_detail(request, pk):
    board = get_object_or_404(Board, pk=pk)
    if not board.can_access(request.user):
        return HttpResponseForbidden()
    annotated_cards = Card.objects.annotate(
        comment_count=Count('comments', distinct=True),
        subtask_total=Count('subtasks', distinct=True),
        subtask_done=Count('subtasks', filter=Q(subtasks__is_done=True), distinct=True),
    ).select_related('assignee', 'creator')
    columns = board.columns.prefetch_related(
        Prefetch('cards', queryset=annotated_cards)
    )
    return render(request, 'kanban/board.html', {'board': board, 'columns': columns})


@login_required
def board_create(request):
    if not (request.user.can_see_all or request.user.role == request.user.Role.GERENTE):
        return HttpResponseForbidden()
    form = BoardForm(request.POST or None, user=request.user)
    if request.method == 'POST' and form.is_valid():
        board = form.save(commit=False)
        board.created_by = request.user
        board.save()
        form.save_m2m()
        Column.objects.bulk_create([
            Column(board=board, name='A Fazer',      order=0, color='#64748b'),
            Column(board=board, name='Em Andamento', order=1, color='#3b82f6'),
            Column(board=board, name='Em Revisão',   order=2, color='#f59e0b'),
            Column(board=board, name='Concluído',    order=3, color='#22c55e'),
        ])
        messages.success(request, f'Quadro "{board.name}" criado.')
        return redirect('kanban:board_detail', pk=board.pk)
    return render(request, 'kanban/board_form.html', {'form': form, 'title': 'Novo Quadro'})


@login_required
def card_detail(request, board_pk, pk):
    board = get_object_or_404(Board, pk=board_pk)
    if not board.can_access(request.user):
        return HttpResponseForbidden()
    card = get_object_or_404(Card, pk=pk, column__board=board)

    comment_form = CardCommentForm()
    subtask_form = SubTaskForm()

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'comment':
            comment_form = CardCommentForm(request.POST)
            if comment_form.is_valid():
                c = comment_form.save(commit=False)
                c.card = card
                c.author = request.user
                c.save()
                CardActivity.objects.create(card=card, user=request.user, action='Comentou no card')
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
                try:
                    _notify_subtask(st, request.user)
                except Exception:
                    pass
                messages.success(request, f'Sub-tarefa "{st.title}" adicionada.')
                return redirect('kanban:card_detail', board_pk=board.pk, pk=card.pk)

    subtasks = card.subtasks.select_related('assignee', 'target_department')
    done_count = subtasks.filter(is_done=True).count()
    return render(request, 'kanban/card_detail.html', {
        'board': board,
        'card': card,
        'comment_form': comment_form,
        'subtask_form': subtask_form,
        'subtasks': subtasks,
        'done_count': done_count,
    })


@login_required
@require_POST
def subtask_toggle(request, pk):
    st = get_object_or_404(SubTask, pk=pk)
    board = st.card.column.board
    if not board.can_access(request.user):
        return HttpResponseForbidden()
    st.is_done = not st.is_done
    st.save(update_fields=['is_done'])
    CardActivity.objects.create(
        card=st.card, user=request.user,
        action=f'{"Concluiu" if st.is_done else "Reabriu"} sub-tarefa: {st.title}'
    )
    return redirect('kanban:card_detail', board_pk=board.pk, pk=st.card.pk)


@login_required
@require_POST
def subtask_delete(request, pk):
    st = get_object_or_404(SubTask, pk=pk)
    board = st.card.column.board
    if not board.can_access(request.user):
        return HttpResponseForbidden()
    card_pk = st.card.pk
    st.delete()
    return redirect('kanban:card_detail', board_pk=board.pk, pk=card_pk)


@login_required
def card_create(request, board_pk):
    board = get_object_or_404(Board, pk=board_pk)
    if not board.can_access(request.user):
        return HttpResponseForbidden()
    form = CardForm(request.POST or None, board=board)
    if request.method == 'POST' and form.is_valid():
        card = form.save(commit=False)
        card.creator = request.user
        last = Card.objects.filter(column=card.column).order_by('-order').first()
        card.order = (last.order + 1) if last else 0
        card.save()
        CardActivity.objects.create(card=card, user=request.user, action='Criou o card')
        AuditLog.log(
            request.user, AuditLog.Action.CARD_CREATE,
            resource_type='Card', resource_id=card.pk,
            ip=AuditMiddleware.get_client_ip(request),
        )
        _notify_card(card, request.user, created=True)
        if request.headers.get('HX-Request'):
            columns = board.columns.prefetch_related('cards__assignee')
            return render(request, 'kanban/partials/board_columns.html', {'board': board, 'columns': columns})
        return redirect('kanban:board_detail', pk=board.pk)
    return render(request, 'kanban/card_form.html', {'form': form, 'board': board, 'title': 'Novo Card'})


@login_required
def card_edit(request, board_pk, pk):
    board = get_object_or_404(Board, pk=board_pk)
    if not board.can_access(request.user):
        return HttpResponseForbidden()
    card = get_object_or_404(Card, pk=pk, column__board=board)
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

    data = json.loads(request.body)
    column_id = data.get('column_id')
    order = data.get('order', 0)
    col = get_object_or_404(Column, pk=column_id, board=board)
    old_col = card.column
    card.column = col
    card.order = order
    card.save(update_fields=['column', 'order'])

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
    return JsonResponse({'status': 'ok'})


@login_required
@require_POST
def card_delete(request, board_pk, pk):
    board = get_object_or_404(Board, pk=board_pk)
    if not board.can_access(request.user):
        return HttpResponseForbidden()
    card = get_object_or_404(Card, pk=pk, column__board=board)
    AuditLog.log(
        request.user, AuditLog.Action.CARD_DELETE,
        resource_type='Card', resource_id=card.pk,
        ip=AuditMiddleware.get_client_ip(request),
        title=card.title,
    )
    card.delete()
    messages.success(request, 'Card excluído.')
    return redirect('kanban:board_detail', pk=board.pk)


def _notify_subtask(subtask, actor):
    card = subtask.card
    board = card.column.board
    link = f'/kanban/{board.pk}/card/{card.pk}/'

    if subtask.assignee and subtask.assignee != actor:
        Notification.send(
            user=subtask.assignee, actor=actor,
            ntype=Notification.Type.CARD_ASSIGNED,
            title=f'Sub-tarefa atribuída a você em "{card.title}"',
            body=subtask.title, link=link,
        )

    if subtask.target_department:
        dept = subtask.target_department
        targets = set()
        if dept.leader and dept.leader != actor:
            targets.add(dept.leader)
        for mgr in CustomUser.objects.filter(role=CustomUser.Role.GERENTE, department=dept, is_active=True):
            if mgr != actor:
                targets.add(mgr)
        for user in targets:
            Notification.send(
                user=user, actor=actor,
                ntype=Notification.Type.CARD_CROSS,
                title=f'Nova sub-tarefa para {dept.name}',
                body=f'"{subtask.title}" em "{card.title}"', link=link,
            )


def _notify_card(card, actor, created: bool):
    """
    Envia notificações ao criar/reatribuir um card.

    Regras:
    - Se o card tem responsável (assignee) diferente do criador → notifica o responsável.
    - Se o board pertence a um departamento diferente do criador → notifica os líderes
      desse departamento (campo leader + usuários com role GERENTE no dept).
    - Se o board é global e há responsável → apenas notifica o responsável.
    """
    board = card.column.board
    link = f'/kanban/{board.pk}/card/{card.pk}/'
    verb = 'criou' if created else 'atualizou'

    targets = set()

    # Notifica o responsável direto
    if card.assignee and card.assignee != actor:
        Notification.send(
            user=card.assignee,
            actor=actor,
            ntype=Notification.Type.CARD_ASSIGNED,
            title=f'{actor.get_full_name() or actor.email} {verb} um card para você',
            body=card.title,
            link=link,
        )
        targets.add(card.assignee)

    # Notifica líderes do departamento-alvo quando o card é cross-dept
    if board.department and board.department != actor.department:
        dept = board.department
        leaders = set()

        if dept.leader and dept.leader != actor:
            leaders.add(dept.leader)

        for mgr in CustomUser.objects.filter(
            role=CustomUser.Role.GERENTE,
            department=dept,
            is_active=True,
        ):
            if mgr != actor:
                leaders.add(mgr)

        for leader in leaders:
            if leader not in targets:
                Notification.send(
                    user=leader,
                    actor=actor,
                    ntype=Notification.Type.CARD_CROSS,
                    title=f'Card cross-departamento em {dept.name}',
                    body=f'{actor.get_full_name() or actor.email} {verb} o card "{card.title}"',
                    link=link,
                )

    # Se o board é do próprio departamento do ator mas sem responsável →
    # notifica os líderes do dept (para visibilidade)
    elif board.department and board.department == actor.department and not card.assignee and created:
        dept = board.department
        for mgr in CustomUser.objects.filter(
            role=CustomUser.Role.GERENTE,
            department=dept,
            is_active=True,
        ):
            if mgr != actor and mgr not in targets:
                Notification.send(
                    user=mgr,
                    actor=actor,
                    ntype=Notification.Type.CARD_DEPT,
                    title=f'Novo card em {dept.name}',
                    body=card.title,
                    link=link,
                )
