from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST

from core.models import CustomUser, AuditLog
from core.middleware import AuditMiddleware
from .models import Conversation, Message, MessageRead, MessageAnexo
from .forms import NewConversationForm, MessageForm


@login_required
def inbox(request):
    convs = Conversation.objects.filter(participants=request.user).order_by('-updated_at')
    conv_data = []
    for conv in convs:
        conv_data.append({
            'conv': conv,
            'display_name': conv.get_display_name(request.user),
            'last_message': conv.get_last_message(),
            'unread': conv.unread_count(request.user),
        })
    return render(request, 'mensagens/inbox.html', {'conv_data': conv_data})


@login_required
def conversation(request, pk):
    conv = get_object_or_404(Conversation, pk=pk)
    if not conv.participants.filter(pk=request.user.pk).exists():
        return HttpResponseForbidden()

    # mark all as read
    unread_msgs = conv.messages.filter(is_deleted=False).exclude(reads__user=request.user).exclude(sender=request.user)
    for msg in unread_msgs:
        MessageRead.objects.get_or_create(message=msg, user=request.user)

    form = MessageForm()
    messages_qs = conv.messages.filter(is_deleted=False).select_related('sender').prefetch_related('anexos')
    return render(request, 'mensagens/conversation.html', {
        'conv': conv,
        'display_name': conv.get_display_name(request.user),
        'messages_qs': messages_qs,
        'form': form,
    })


@login_required
def messages_poll(request, pk):
    """HTMX endpoint — returns only the messages partial."""
    conv = get_object_or_404(Conversation, pk=pk)
    if not conv.participants.filter(pk=request.user.pk).exists():
        return HttpResponseForbidden()

    unread_msgs = conv.messages.filter(is_deleted=False).exclude(reads__user=request.user).exclude(sender=request.user)
    for msg in unread_msgs:
        MessageRead.objects.get_or_create(message=msg, user=request.user)

    messages_qs = conv.messages.filter(is_deleted=False).select_related('sender')
    return render(request, 'mensagens/partials/messages_list.html', {
        'messages_qs': messages_qs,
        'conv': conv,
    })


@login_required
@require_POST
def send_message(request, pk):
    conv = get_object_or_404(Conversation, pk=pk)
    if not conv.participants.filter(pk=request.user.pk).exists():
        return HttpResponseForbidden()

    form = MessageForm(request.POST)
    arquivo = request.FILES.get('arquivo')
    if form.is_valid() and (form.cleaned_data.get('content') or arquivo):
        msg = Message.objects.create(
            conversation=conv,
            sender=request.user,
            content=form.cleaned_data.get('content', ''),
        )
        if arquivo:
            from core.validators import validate_file_extension, validate_file_size
            from django.core.exceptions import ValidationError
            try:
                validate_file_extension(arquivo)
                validate_file_size(arquivo)
                MessageAnexo.objects.create(
                    message=msg,
                    arquivo=arquivo,
                    nome_original=arquivo.name,
                    enviado_por=request.user,
                )
            except ValidationError:
                pass
        MessageRead.objects.create(message=msg, user=request.user)
        conv.save()
        AuditLog.log(
            request.user, AuditLog.Action.MSG_SEND,
            resource_type='Conversation', resource_id=conv.pk,
            ip=AuditMiddleware.get_client_ip(request),
        )

    messages_qs = conv.messages.filter(is_deleted=False).select_related('sender').prefetch_related('anexos')
    return render(request, 'mensagens/partials/messages_list.html', {
        'messages_qs': messages_qs,
        'conv': conv,
    })


@login_required
def new_conversation(request):
    form = NewConversationForm(request.POST or None, current_user=request.user)
    if request.method == 'POST' and form.is_valid():
        data = form.cleaned_data
        participants = list(data['participants'])
        is_group = data.get('is_group', False) or len(participants) > 1

        if not is_group and len(participants) == 1:
            existing = Conversation.objects.filter(
                is_group=False,
                participants=request.user
            ).filter(participants=participants[0])
            if existing.exists():
                return redirect('mensagens:conversation', pk=existing.first().pk)

        conv = Conversation.objects.create(
            is_group=is_group,
            name=data.get('name', ''),
            created_by=request.user,
        )
        conv.participants.add(request.user, *participants)
        return redirect('mensagens:conversation', pk=conv.pk)

    return render(request, 'mensagens/new_conversation.html', {'form': form})


@login_required
@require_POST
def delete_message(request, pk):
    msg = get_object_or_404(Message, pk=pk)
    if msg.sender != request.user and not request.user.can_manage_users:
        return HttpResponseForbidden()
    msg.is_deleted = True
    msg.save(update_fields=['is_deleted'])
    AuditLog.log(
        request.user, AuditLog.Action.MSG_DELETE,
        resource_type='Message', resource_id=msg.pk,
        ip=AuditMiddleware.get_client_ip(request),
    )
    messages_qs = msg.conversation.messages.filter(is_deleted=False).select_related('sender')
    return render(request, 'mensagens/partials/messages_list.html', {
        'messages_qs': messages_qs,
        'conv': msg.conversation,
    })
