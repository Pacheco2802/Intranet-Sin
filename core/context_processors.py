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

    return {
        'unread_messages_count': unread_count,
        'pending_count': pending_count,
        'notification_count': notification_count,
    }
