from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = 'core'

    def ready(self):
        from django.db.models.signals import post_save
        from django.dispatch import receiver

        @receiver(post_save, sender='core.Department')
        def bootstrap_department(sender, instance, created, **kwargs):
            if not created:
                return
            from core.models import Team
            from kanban.models import Board, Column

            # Auto-create team
            team, _ = Team.objects.get_or_create(
                department=instance,
                defaults={
                    'name': instance.name,
                    'is_general': False,
                    'is_protected': True,
                },
            )

            # Auto-create internal kanban board
            board, board_created = Board.objects.get_or_create(
                department=instance,
                is_auto=True,
                defaults={
                    'name': f'Kanban — {instance.name}',
                    'is_cross_department': False,
                    'is_global': False,
                    'created_by': None,
                },
            )
            if board_created:
                Column.objects.bulk_create([
                    Column(board=board, name='A Fazer',      order=0, color='#64748b'),
                    Column(board=board, name='Em Andamento', order=1, color='#3b82f6'),
                    Column(board=board, name='Em Revisão',   order=2, color='#f59e0b'),
                    Column(board=board, name='Concluído',    order=3, color='#22c55e'),
                ])
