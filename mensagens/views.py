from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import render, redirect, get_object_or_404
from django.utils.timezone import localtime, localdate
from django.views.decorators.http import require_POST

from core.models import CustomUser, AuditLog
from core.middleware import AuditMiddleware
from .models import Conversation, Message, MessageRead, MessageAnexo
from .forms import NewConversationForm, MessageForm

MESSAGES_PER_PAGE = 50


def _build_feed(messages_list):
    """Converts list of Message objects to feed items with day separators."""
    today = localdate()
    yesterday = today - timedelta(days=1)
    items = []
    current_day = None
    for msg in messages_list:
        msg_day = localtime(msg.sent_at).date()
        if msg_day != current_day:
            if msg_day == today:
                label = 'Hoje'
            elif msg_day == yesterday:
                label = 'Ontem'
            else:
                label = msg_day.strftime('%d/%m/%Y')
            items.append({'type': 'separator', 'label': label})
            current_day = msg_day
        items.append({'type': 'message', 'msg': msg})
    return items


def _get_paged_messages(conv, before_id=None):
    """Returns (msgs_list, has_more, oldest_id) for a conversation."""
    qs = conv.messages.filter(is_deleted=False)
    if before_id:
        qs = qs.filter(pk__lt=before_id)
    qs = qs.select_related('sender').prefetch_related('anexos').order_by('sent_at')
    total = qs.count()
    has_more = total > MESSAGES_PER_PAGE
    msgs = list(qs[total - MESSAGES_PER_PAGE:] if has_more else qs)
    oldest_id = msgs[0].pk if msgs else None
    return msgs, has_more, oldest_id


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

    unread_msgs = conv.messages.filter(is_deleted=False).exclude(reads__user=request.user).exclude(sender=request.user)
    for msg in unread_msgs:
        MessageRead.objects.get_or_create(message=msg, user=request.user)

    msgs, has_more, oldest_id = _get_paged_messages(conv)
    feed = _build_feed(msgs)
    return render(request, 'mensagens/conversation.html', {
        'conv': conv,
        'display_name': conv.get_display_name(request.user),
        'feed': feed,
        'has_more': has_more,
        'oldest_id': oldest_id,
        'form': MessageForm(),
    })


@login_required
def messages_poll(request, pk):
    """HTMX polling endpoint — returns last N messages with day separators."""
    conv = get_object_or_404(Conversation, pk=pk)
    if not conv.participants.filter(pk=request.user.pk).exists():
        return HttpResponseForbidden()

    unread_msgs = conv.messages.filter(is_deleted=False).exclude(reads__user=request.user).exclude(sender=request.user)
    for msg in unread_msgs:
        MessageRead.objects.get_or_create(message=msg, user=request.user)

    msgs, _, _ = _get_paged_messages(conv)
    feed = _build_feed(msgs)
    return render(request, 'mensagens/partials/messages_list.html', {'feed': feed, 'conv': conv})


@login_required
def messages_load_more(request, pk):
    """HTMX endpoint — loads older messages before a given message ID."""
    conv = get_object_or_404(Conversation, pk=pk)
    if not conv.participants.filter(pk=request.user.pk).exists():
        return HttpResponseForbidden()

    before_id = request.GET.get('before_id')
    if not before_id:
        return HttpResponse('')

    msgs, has_more, oldest_id = _get_paged_messages(conv, before_id=before_id)
    feed = _build_feed(msgs)
    return render(request, 'mensagens/partials/messages_older.html', {
        'feed': feed,
        'has_more': has_more,
        'oldest_id': oldest_id,
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

    msgs, _, _ = _get_paged_messages(conv)
    feed = _build_feed(msgs)
    return render(request, 'mensagens/partials/messages_list.html', {'feed': feed, 'conv': conv})


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
    msgs, _, _ = _get_paged_messages(msg.conversation)
    feed = _build_feed(msgs)
    return render(request, 'mensagens/partials/messages_list.html', {'feed': feed, 'conv': msg.conversation})
