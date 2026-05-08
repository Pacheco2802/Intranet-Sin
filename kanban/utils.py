from .models import Board, Column, Card, CardActivity


def _get_or_create_first_column(department, creator):
    board = Board.objects.filter(department=department).order_by('is_auto', 'created_at').first()
    if not board:
        board = Board.objects.create(
            name=f'Quadro — {department.name}',
            department=department,
            is_auto=True,
            created_by=creator,
        )
        Column.objects.create(board=board, name='A Fazer', order=0, color='#64748b')
        Column.objects.create(board=board, name='Em Andamento', order=1, color='#f59e0b')
        Column.objects.create(board=board, name='Concluído', order=2, color='#22c55e')

    column = board.columns.order_by('order').first()
    if not column:
        column = Column.objects.create(board=board, name='A Fazer', order=0)
    return column


def criar_card_automatico(department, title, description, creator, assignee=None, tags='', subtask=None, atendimento_id=None):
    """Cria um card na primeira coluna do board do departamento. Cria o board se não existir."""
    if not department:
        return None
    try:
        column = _get_or_create_first_column(department, creator)
        card = Card.objects.create(
            column=column,
            title=title,
            description=description,
            creator=creator,
            assignee=assignee,
            tags=tags,
            source_subtask=subtask,
            source_atendimento_id=atendimento_id,
        )
        CardActivity.objects.create(card=card, user=creator, action='Card criado automaticamente')
        return card
    except Exception:
        return None


def mover_card_para_ultima_coluna(card):
    """Move o card para a coluna 'Concluído' (busca pelo nome, fallback para última)."""
    try:
        board = card.column.board
        coluna = (
            board.columns.filter(name__icontains='conclu').first()
            or board.columns.order_by('-order').first()
        )
        if coluna and card.column_id != coluna.pk:
            card.column = coluna
            card.save(update_fields=['column'])
    except Exception:
        pass


def mover_card_para_primeira_coluna(card):
    """Move o card para a primeira coluna que não seja 'Concluído'."""
    try:
        board = card.column.board
        coluna = (
            board.columns.exclude(name__icontains='conclu').order_by('order').first()
            or board.columns.order_by('order').first()
        )
        if coluna and card.column_id != coluna.pk:
            card.column = coluna
            card.save(update_fields=['column'])
    except Exception:
        pass
