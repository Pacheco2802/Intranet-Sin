import json
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Count, Q
from django.db.models import Prefetch
from django.http import JsonResponse, HttpResponseForbidden
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST

from core.models import AuditLog, Notification, CustomUser, Department
from core.middleware import AuditMiddleware
from core.validators import validate_file_extension, validate_file_size
from .models import Board, Column, Card, CardComment, CardActivity, SubTask, SubTaskAnexo, CardAnexo
from .forms import BoardForm, ColumnForm, CardForm, CardCommentForm, SubTaskForm
from .utils import criar_card_automatico, mover_card_para_ultima_coluna, mover_card_para_primeira_coluna


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
    board_members = CustomUser.objects.filter(
        assigned_cards__column__board=board, is_active=True
    ).distinct().order_by('first_name')
    return render(request, 'kanban/board.html', {
        'board': board,
        'columns': columns,
        'board_members': board_members,
    })


@login_required
def board_create(request):
    if not request.user.can_see_all:
        return HttpResponseForbidden()
    form = BoardForm(request.POST or None, user=request.user)
    if request.method == 'POST' and form.is_valid():
        board = form.save(commit=False)
        board.created_by = request.user
        board.save()
        form.save_m2m()
        Column.objects.bulk_create([
            Column(board=board, name='A Fazer',      order=0, color='#64748b', column_type=Column.ColumnType.A_FAZER),
            Column(board=board, name='Em Andamento', order=1, color='#3b82f6', column_type=Column.ColumnType.EM_ANDAMENTO),
            Column(board=board, name='Status Final', order=2, color='#22c55e', column_type=Column.ColumnType.STATUS_FINAL),
        ])
        messages.success(request, f'Quadro "{board.name}" criado.')
        return redirect('kanban:board_detail', pk=board.pk)
    return render(request, 'kanban/board_form.html', {'form': form, 'title': 'Novo Quadro'})


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

    comment_form = CardCommentForm()
    subtask_form = SubTaskForm()

    if request.method == 'POST':
        if not is_member:
            return HttpResponseForbidden()
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

    subtasks = card.subtasks.select_related('assignee', 'target_department').prefetch_related('anexos__enviado_por')
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
    card = get_object_or_404(Card, pk=pk, column__board=board)
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
    card.save(update_fields=['column', 'order'])
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
    from datetime import timedelta
    today = tz.now().date()

    annotated_cards = Card.objects.annotate(
        comment_count=Count('comments', distinct=True),
        subtask_total=Count('subtasks', distinct=True),
        subtask_done=Count('subtasks', filter=Q(subtasks__is_done=True), distinct=True),
    ).select_related('assignee', 'creator')

    priority = request.GET.get('priority')
    assignee_id = request.GET.get('assignee')
    prazo = request.GET.get('prazo')

    if priority:
        annotated_cards = annotated_cards.filter(priority=priority)
    if assignee_id:
        annotated_cards = annotated_cards.filter(assignee_id=assignee_id)
    if prazo == 'vencidos':
        annotated_cards = annotated_cards.filter(due_date__lt=today)
    elif prazo == 'hoje':
        annotated_cards = annotated_cards.filter(due_date=today)
    elif prazo == 'semana':
        annotated_cards = annotated_cards.filter(due_date__gte=today, due_date__lte=today + timedelta(days=7))

    columns = board.columns.prefetch_related(
        Prefetch('cards', queryset=annotated_cards)
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

    cards = col.cards.select_related('assignee', 'creator').order_by('-updated_at')

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


@login_required
def board_edit(request, pk):
    if not request.user.is_admin_ti:
        return HttpResponseForbidden()
    board = get_object_or_404(Board, pk=pk)
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
    board.delete()
    messages.success(request, f'Quadro "{name}" excluído.')
    return redirect('kanban:board_list')


@login_required
def column_create(request, board_pk):
    if not request.user.is_admin_ti:
        return HttpResponseForbidden()
    board = get_object_or_404(Board, pk=board_pk)
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
    from core.models import Department

    today = timezone.now().date()
    CT = Column.ColumnType

    all_cards = Card.objects.select_related('column')
    total = all_cards.count()
    a_fazer = all_cards.filter(column__column_type=CT.A_FAZER).count()
    em_andamento = all_cards.filter(column__column_type=CT.EM_ANDAMENTO).count()
    status_final = all_cards.filter(column__column_type=CT.STATUS_FINAL).count()

    ativas_com_prazo = all_cards.exclude(column__column_type=CT.STATUS_FINAL).filter(due_date__isnull=False)
    no_prazo = ativas_com_prazo.filter(due_date__gte=today).count()
    vencidos = ativas_com_prazo.filter(due_date__lt=today).count()

    concluidos = all_cards.filter(final_status='concluido').count()
    nao_concluidos = all_cards.filter(final_status='nao_concluido').count()
    cancelados = all_cards.filter(final_status='cancelado').count()

    from django.db.models import F
    concluidos_com_atraso = all_cards.filter(
        final_status__in=['concluido', 'nao_concluido', 'cancelado'],
        due_date__isnull=False,
        completed_at__isnull=False,
    ).filter(completed_at__date__gt=F('due_date')).count()

    dept_stats = []
    for dept in Department.objects.filter(boards__isnull=False).distinct().order_by('name'):
        dc = Card.objects.filter(column__board__department=dept)
        dept_stats.append({
            'dept': dept,
            'total': dc.count(),
            'a_fazer': dc.filter(column__column_type=CT.A_FAZER).count(),
            'em_andamento': dc.filter(column__column_type=CT.EM_ANDAMENTO).count(),
            'status_final': dc.filter(column__column_type=CT.STATUS_FINAL).count(),
            'vencidos': dc.exclude(column__column_type=CT.STATUS_FINAL).filter(
                due_date__lt=today, due_date__isnull=False
            ).count(),
            'concluidos_com_atraso': dc.filter(
                final_status__in=['concluido', 'nao_concluido', 'cancelado'],
                due_date__isnull=False,
                completed_at__isnull=False,
            ).filter(completed_at__date__gt=F('due_date')).count(),
        })

    return render(request, 'kanban/analise.html', {
        'total': total,
        'a_fazer': a_fazer,
        'em_andamento': em_andamento,
        'status_final': status_final,
        'no_prazo': no_prazo,
        'vencidos': vencidos,
        'concluidos': concluidos,
        'nao_concluidos': nao_concluidos,
        'cancelados': cancelados,
        'concluidos_com_atraso': concluidos_com_atraso,
        'dept_stats': dept_stats,
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
