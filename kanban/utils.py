from django.utils import timezone

from .models import Board, Column, Card, CardActivity


# ─────────────────────────────────────────────────────────────────────────────
# AJUSTES DE EXIBIÇÃO DO BOARD
#
#   COLUMN_ITEM_LIMIT → quantos itens cada coluna ativa mostra antes do
#                       botão "ver mais". Aumente/diminua aqui. (0 = sem limite)
#
#   STALE_DAYS        → a partir de quantos dias parado na mesma coluna o card
#                       recebe o aviso de "envelhecimento" (⏱).
#
#   O LIMITE WIP (trabalho em andamento) NÃO fica aqui: é por coluna, no campo
#   "Limite WIP" ao editar a coluna (lápis no cabeçalho) ou no Django admin.
#   0 = sem limite.
# ─────────────────────────────────────────────────────────────────────────────
COLUMN_ITEM_LIMIT = 20
STALE_DAYS = 5

_PRIORITY_ORDER = {'URGENT': 0, 'HIGH': 1, 'MEDIUM': 2, 'LOW': 3, '': 4}


def _card_of(item):
    return item['card'] if item['type'] == 'card' else item['cards'][0]


def _item_sort_key(item, sort_by):
    card = _card_of(item)
    if sort_by == 'priority':
        return (_PRIORITY_ORDER.get(getattr(card, 'priority', ''), 4), -card.created_at.timestamp())
    if sort_by == 'due_date':
        d = card.due_date.toordinal() if card.due_date else 99999
        return (d, -card.created_at.timestamp())
    if sort_by == 'title':
        t = card.title if item['type'] == 'card' else item.get('parent_title', '')
        return t.lower()
    if sort_by == 'updated':
        return -card.updated_at.timestamp()
    # padrão: order field, depois mais novo primeiro
    return (item['sort'], -card.created_at.timestamp())


def _final_sort_key(item):
    card = _card_of(item)
    ts = card.completed_at.timestamp() if card.completed_at else card.updated_at.timestamp()
    return -ts


def build_grouped_columns(columns, limit=COLUMN_ITEM_LIMIT, sort_by=''):
    """Converte colunas (com cards prefetchados/anotados) em itens agrupados.

    Cada coluna recebe os atributos:
      - grouped_items: lista de itens, onde cada item é
          {'type': 'card', 'card': Card, 'sort': int, 'overflow': bool}  ou
          {'type': 'group', 'parent_id', 'parent_title', 'parent_board_id',
           'cards': [Card, ...], 'done': int, 'total': int, 'sort': int, 'overflow': bool}
      - is_final: bool (coluna de status final)
      - total_items: int (nº de itens após agrupar)
      - extra_count: int (itens além do limite, em colunas não-finais)

    Cards com source_subtask são agrupados pelo card-pai (source_subtask.card).
    """
    cols = list(columns)
    today = timezone.now().date()
    for col in cols:
        cards = list(col.cards.all())   # já anotados + select_related
        col.is_final = (col.column_type == Column.ColumnType.STATUS_FINAL)
        items, groups = [], {}
        for card in cards:
            # ── Envelhecimento: dias parado nesta coluna (proxy: updated_at) ──
            card.days_in_column = (today - card.updated_at.date()).days
            card.is_stale = (not col.is_final) and card.days_in_column >= STALE_DAYS

            parent_id = card.source_subtask.card_id if card.source_subtask_id else None
            if parent_id:
                g = groups.get(parent_id)
                if not g:
                    parent = card.source_subtask.card
                    g = {
                        'type': 'group',
                        'parent_id': parent_id,
                        'parent_title': parent.title,
                        'parent_board_id': parent.column.board_id,
                        'cards': [],
                        'done': 0,
                        'total': 0,
                        'sort': card.order,
                    }
                    groups[parent_id] = g
                    items.append(g)
                g['cards'].append(card)
                g['total'] += 1
                if card.source_subtask.is_done:
                    g['done'] += 1
                if card.order < g['sort']:
                    g['sort'] = card.order
            else:
                items.append({'type': 'card', 'card': card, 'sort': card.order})

        if col.is_final:
            items.sort(key=_final_sort_key)
        elif sort_by:
            items.sort(key=lambda i: _item_sort_key(i, sort_by))
        else:
            items.sort(key=lambda i: i['sort'])

        # ── WIP: nº real de cards x limite da coluna (0 = sem limite) ──
        col.card_count = len(cards)
        col.wip_exceeded = bool(col.wip_limit) and col.card_count > col.wip_limit

        col.total_items = len(items)
        if not col.is_final:
            for idx, it in enumerate(items):
                it['overflow'] = idx >= limit
            col.extra_count = max(0, len(items) - limit)
        else:
            for it in items:
                it['overflow'] = False
            col.extra_count = 0
        col.grouped_items = items
    return cols


def _get_or_create_first_column(department, creator):
    board = Board.objects.filter(department=department).order_by('is_auto', 'created_at').first()
    if not board:
        board = Board.objects.create(
            name=f'Quadro — {department.name}',
            department=department,
            is_auto=True,
            created_by=creator,
        )
        Column.objects.create(board=board, name='A Fazer',       order=0, color='#64748b', column_type=Column.ColumnType.A_FAZER)
        Column.objects.create(board=board, name='Em Andamento',  order=1, color='#f59e0b', column_type=Column.ColumnType.EM_ANDAMENTO)
        Column.objects.create(board=board, name='Status Final',  order=2, color='#22c55e', column_type=Column.ColumnType.STATUS_FINAL)

    column = board.columns.order_by('order').first()
    if not column:
        column = Column.objects.create(board=board, name='A Fazer', order=0, column_type=Column.ColumnType.A_FAZER)
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
    """Move o card para a coluna de Status Final (busca por column_type, fallback por nome)."""
    try:
        board = card.column.board
        coluna = (
            board.columns.filter(column_type=Column.ColumnType.STATUS_FINAL).first()
            or board.columns.filter(name__icontains='final').first()
            or board.columns.filter(name__icontains='conclu').first()
            or board.columns.order_by('-order').first()
        )
        if coluna and card.column_id != coluna.pk:
            card.column = coluna
            card.save(update_fields=['column'])
    except Exception:
        pass


def mover_card_para_primeira_coluna(card):
    """Move o card para a primeira coluna A Fazer."""
    try:
        board = card.column.board
        coluna = (
            board.columns.filter(column_type=Column.ColumnType.A_FAZER).first()
            or board.columns.exclude(column_type=Column.ColumnType.STATUS_FINAL).order_by('order').first()
            or board.columns.order_by('order').first()
        )
        if coluna and card.column_id != coluna.pk:
            card.column = coluna
            card.save(update_fields=['column'])
    except Exception:
        pass
