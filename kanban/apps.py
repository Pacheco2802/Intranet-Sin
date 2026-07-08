from django.apps import AppConfig


class KanbanConfig(AppConfig):
    name = 'kanban'

    def ready(self):
        from . import signals  # noqa: F401 — registra os receivers de limpeza de arquivos
