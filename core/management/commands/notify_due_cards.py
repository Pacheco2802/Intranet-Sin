from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils.timezone import now
from core.models import Notification
from kanban.models import Card, Column


class Command(BaseCommand):
    help = 'Envia notificações para cards vencidos ou com prazo para hoje/amanhã'

    def handle(self, *args, **options):
        today = now().date()
        tomorrow = today + timedelta(days=1)

        active_column_types = [Column.ColumnType.A_FAZER, Column.ColumnType.EM_ANDAMENTO]
        active_cards = Card.objects.filter(
            column__column_type__in=active_column_types,
            due_date__isnull=False,
        ).select_related('assignee', 'column__board__department', 'creator')

        overdue = active_cards.filter(due_date__lt=today)
        due_today = active_cards.filter(due_date=today)
        due_tomorrow = active_cards.filter(due_date=tomorrow)

        sent = 0

        for card in overdue:
            days = (today - card.due_date).days
            sent += self._notify(card, f'Prazo VENCIDO há {days} dia(s)', overdue=True)

        for card in due_today:
            sent += self._notify(card, 'Prazo vence HOJE', overdue=True)

        for card in due_tomorrow:
            sent += self._notify(card, 'Prazo vence amanhã', overdue=False)

        self.stdout.write(self.style.SUCCESS(f'{sent} notificação(ões) enviada(s).'))

    def _notify(self, card, prazo_msg: str, overdue: bool) -> int:
        from kanban.views import _PRIORITY_PREFIX
        board = card.column.board
        link = f'/kanban/{board.pk}/card/{card.pk}/'
        prefix = _PRIORITY_PREFIX.get(card.priority, '')
        title = f'{prefix}{prazo_msg}: "{card.title}"'
        body = f'Prioridade: {card.get_priority_display()}'
        sent = 0

        targets = set()
        if card.assignee:
            targets.add(card.assignee)

        # Notifica também líderes/gerentes do departamento
        if board.department:
            dept = board.department
            if dept.leader:
                targets.add(dept.leader)
            from core.models import CustomUser
            for mgr in CustomUser.objects.filter(
                role=CustomUser.Role.GERENTE, department=dept, is_active=True
            ):
                targets.add(mgr)

        for user in targets:
            Notification.objects.create(
                user=user,
                actor=card.creator,
                type=Notification.Type.CARD_ASSIGNED if user == card.assignee else Notification.Type.CARD_DEPT,
                title=title,
                body=body,
                link=link,
            )
            sent += 1

        return sent
