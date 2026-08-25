from mensagens.models import Message, Conversation


def global_context(request):
    if not request.user.is_authenticated:
        return {}

    unread_count = 0
    try:
        my_convs = Conversation.objects.filter(participants=request.user)
        for conv in my_convs:
            unread_count += conv.messages.filter(
                is_deleted=False
            ).exclude(
                reads__user=request.user
            ).exclude(
                sender=request.user
            ).count()
    except Exception:
        pass

    pending_count = 0
    if request.user.can_manage_users:
        from core.models import CustomUser
        pending_count = CustomUser.objects.filter(is_approved=False, is_active=False).count()

    from core.models import Notification
    notification_count = Notification.objects.filter(user=request.user, is_read=False).count()

    projetos_unread_count = 0
    try:
        from kanban.models import Board
        project_pks = list(
            Board.objects.filter(is_cross_department=True).values_list('pk', flat=True)
        )
        if project_pks:
            pattern = r'^/kanban/(' + '|'.join(str(pk) for pk in project_pks) + r')/'
            projetos_unread_count = Notification.objects.filter(
                user=request.user, is_read=False, link__regex=pattern,
            ).count()
    except Exception:
        pass

    comunicados_unread_count = 0
    try:
        from comunicados.models import Comunicado
        from django.db.models import Q
        user_dept_pks = list(request.user.departments.values_list('pk', flat=True))
        qs = Comunicado.objects.filter(is_published=True).exclude(read_by=request.user)
        # Comunicado sem departamento vai para todos; com departamentos, só para os das áreas do usuário.
        qs = qs.filter(Q(departments__isnull=True) | Q(departments__pk__in=user_dept_pks))
        comunicados_unread_count = qs.distinct().count()
    except Exception:
        pass

    chamados_pendentes_count = 0
    if request.user.is_admin_ti or request.user.can_see_all:
        try:
            from chamados.models import Chamado
            chamados_pendentes_count = Chamado.objects.filter(
                status__in=[
                    Chamado.Status.ABERTO,
                    Chamado.Status.EM_ANDAMENTO,
                    Chamado.Status.AGUARDANDO,
                ]
            ).count()
        except Exception:
            pass

    return {
        'unread_messages_count': unread_count,
        'pending_count': pending_count,
        'notification_count': notification_count,
        'projetos_unread_count': projetos_unread_count,
        'comunicados_unread_count': comunicados_unread_count,
        'chamados_pendentes_count': chamados_pendentes_count,
    }
