from django.core.management.base import BaseCommand
from django.utils.timezone import now
from kanban.models import RecurringTask


class Command(BaseCommand):
    help = 'Gera cards automáticos a partir das tarefas recorrentes ativas'

    def handle(self, *args, **options):
        today = now().date()
        tasks = RecurringTask.objects.filter(active=True).select_related('board', 'column', 'assignee')
        generated = 0
        skipped = 0

        for task in tasks:
            if task.should_generate_today(today):
                card = task.generate_card(today)
                self.stdout.write(
                    self.style.SUCCESS(f'  ✔ [{task.get_frequency_display()}] "{card.title}" → {task.board.name}')
                )
                generated += 1
            else:
                skipped += 1

        self.stdout.write(
            self.style.SUCCESS(f'\n{generated} card(s) gerado(s), {skipped} tarefa(s) ignorada(s) (fora do dia).')
        )
