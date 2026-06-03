from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import HttpResponseForbidden
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST
from django.utils import timezone

from core.models import Notification
from core.validators import validate_file_extension, validate_file_size
from .models import Event, EventParticipant, EventDocumento
from .forms import EventForm


def _notify_invite(event, participant_user, actor):
    link = f'/agenda/{event.pk}/'
    start = event.start_datetime.strftime('%d/%m/%Y às %H:%M')
    Notification.send(
        user=participant_user,
        actor=actor,
        ntype=Notification.Type.EVENT_INVITE,
        title=f'Você foi convidado: {event.title}',
        body=f'{start}{" — " + event.location if event.location else ""}',
        link=link,
    )


@login_required
def event_list(request):
    now = timezone.now()
    user = request.user
    upcoming = Event.objects.filter(
        Q(created_by=user) | Q(participants__user=user),
        start_datetime__gte=now,
    ).distinct().order_by('start_datetime')
    past = Event.objects.filter(
        Q(created_by=user) | Q(participants__user=user),
        start_datetime__lt=now,
    ).distinct().order_by('-start_datetime')[:10]
    return render(request, 'agenda/list.html', {'upcoming': upcoming, 'past': past})


@login_required
def event_create(request):
    form = EventForm(request.POST or None, current_user=request.user)
    if request.method == 'POST' and form.is_valid():
        event = form.save(commit=False)
        event.created_by = request.user
        event.save()
        for user in form.cleaned_data['participants']:
            ep = EventParticipant.objects.create(event=event, user=user)
            _notify_invite(event, user, request.user)
            ep.notified_invite = True
            ep.save(update_fields=['notified_invite'])
        messages.success(request, f'Evento "{event.title}" criado.')
        return redirect('agenda:event_detail', pk=event.pk)
    return render(request, 'agenda/event_form.html', {'form': form, 'title': 'Novo Evento'})


@login_required
def event_detail(request, pk):
    event = get_object_or_404(
        Event.objects.prefetch_related('participants__user', 'documentos__enviado_por'),
        pk=pk,
    )
    user = request.user
    is_participant = event.participants.filter(user=user).exists()
    is_creator = event.created_by == user
    if not (is_creator or is_participant or user.can_see_all):
        return HttpResponseForbidden()
    my_participation = event.participants.filter(user=user).first()
    return render(request, 'agenda/event_detail.html', {
        'event': event,
        'my_participation': my_participation,
        'is_creator': is_creator,
        'can_edit': is_creator or user.is_admin_ti,
        'documentos': event.documentos.all(),
    })


@login_required
@require_POST
def evento_documento_upload(request, pk):
    event = get_object_or_404(Event, pk=pk)
    user = request.user
    is_participant = event.participants.filter(user=user).exists()
    if not (event.created_by == user or is_participant or user.can_see_all):
        return HttpResponseForbidden()

    arquivo = request.FILES.get('arquivo')
    titulo = request.POST.get('titulo', '').strip()

    if not arquivo:
        messages.error(request, 'Selecione um arquivo.')
        return redirect('agenda:event_detail', pk=pk)

    if not titulo:
        titulo = arquivo.name

    try:
        validate_file_extension(arquivo)
        validate_file_size(arquivo)
    except ValidationError as e:
        messages.error(request, e.message)
        return redirect('agenda:event_detail', pk=pk)

    EventDocumento.objects.create(
        event=event,
        titulo=titulo,
        arquivo=arquivo,
        nome_original=arquivo.name,
        enviado_por=user,
    )
    messages.success(request, f'Documento "{titulo}" anexado.')
    return redirect('agenda:event_detail', pk=pk)


@login_required
@require_POST
def evento_documento_delete(request, doc_pk):
    doc = get_object_or_404(EventDocumento, pk=doc_pk)
    event_pk = doc.event_id
    user = request.user
    if not (doc.enviado_por == user or doc.event.created_by == user or user.can_see_all):
        return HttpResponseForbidden()
    doc.arquivo.delete(save=False)
    doc.delete()
    messages.success(request, 'Documento removido.')
    return redirect('agenda:event_detail', pk=event_pk)


@login_required
def event_edit(request, pk):
    event = get_object_or_404(Event, pk=pk)
    if not (event.created_by == request.user or request.user.is_admin_ti):
        return HttpResponseForbidden()
    existing_participants = set(event.participants.values_list('user_id', flat=True))
    form = EventForm(request.POST or None, instance=event, current_user=request.user)
    if request.method == 'POST' and form.is_valid():
        event = form.save()
        new_participants = set(u.pk for u in form.cleaned_data['participants'])
        # Add new participants and notify them
        for user in form.cleaned_data['participants']:
            ep, created = EventParticipant.objects.get_or_create(event=event, user=user)
            if created:
                _notify_invite(event, user, request.user)
                ep.notified_invite = True
                ep.save(update_fields=['notified_invite'])
        # Remove participants no longer selected
        event.participants.filter(user_id__in=existing_participants - new_participants).delete()
        messages.success(request, f'Evento "{event.title}" atualizado.')
        return redirect('agenda:event_detail', pk=event.pk)
    return render(request, 'agenda/event_form.html', {'form': form, 'event': event, 'title': f'Editar: {event.title}'})


@login_required
@require_POST
def event_delete(request, pk):
    event = get_object_or_404(Event, pk=pk)
    if not (event.created_by == request.user or request.user.is_admin_ti):
        return HttpResponseForbidden()
    event.delete()
    messages.success(request, 'Evento excluído.')
    return redirect('agenda:event_list')


@login_required
@require_POST
def event_confirm(request, pk):
    event = get_object_or_404(Event, pk=pk)
    ep = get_object_or_404(EventParticipant, event=event, user=request.user)
    action = request.POST.get('action')
    if action == 'confirm':
        ep.status = EventParticipant.Status.CONFIRMED
        label = 'confirmada'
    elif action == 'decline':
        ep.status = EventParticipant.Status.DECLINED
        label = 'recusada'
    else:
        return redirect('agenda:event_detail', pk=pk)
    ep.save(update_fields=['status'])
    # Notify creator
    if event.created_by != request.user:
        Notification.send(
            user=event.created_by,
            actor=request.user,
            ntype=Notification.Type.EVENT_INVITE,
            title=f'{request.user.get_full_name() or request.user.email} {label} presença em "{event.title}"',
            body='',
            link=f'/agenda/{event.pk}/',
        )
    messages.success(request, f'Presença {label}.')
    return redirect('agenda:event_detail', pk=pk)
