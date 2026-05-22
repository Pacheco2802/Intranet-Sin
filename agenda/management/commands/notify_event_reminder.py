from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta

from core.models import Notification
from agenda.models import EventParticipant


class Command(BaseCommand):
    help = 'Envia notificações de lembrete 30 minutos antes dos eventos'

    def handle(self, *args, **options):
        now = timezone.now()
        window_start = now + timedelta(minutes=25)
        window_end = now + timedelta(minutes=35)

        participants = EventParticipant.objects.filter(
            notified_reminder=False,
            event__start_datetime__gte=window_start,
            event__start_datetime__lte=window_end,
        ).select_related('user', 'event__created_by')

        count = 0
        for ep in participants:
            event = ep.event
            start = event.start_datetime.strftime('%H:%M')
            body = f'Começa às {start}'
            if event.location:
                body += f' — {event.location}'
            Notification.send(
                user=ep.user,
                actor=event.created_by,
                ntype=Notification.Type.EVENT_REMINDER,
                title=f'Lembrete: {event.title} em 30 minutos',
                body=body,
                link=f'/agenda/{event.pk}/',
            )
            ep.notified_reminder = True
            ep.save(update_fields=['notified_reminder'])
            count += 1

        # Notificar o próprio criador se ele não for participante
        from agenda.models import Event
        events = Event.objects.filter(
            start_datetime__gte=window_start,
            start_datetime__lte=window_end,
        ).select_related('created_by')
        for event in events:
            already = EventParticipant.objects.filter(event=event, user=event.created_by).exists()
            if not already:
                Notification.objects.get_or_create(
                    user=event.created_by,
                    type=Notification.Type.EVENT_REMINDER,
                    title=f'Lembrete: {event.title} em 30 minutos',
                    is_read=False,
                    defaults={
                        'body': f'Começa às {event.start_datetime.strftime("%H:%M")}' + (f' — {event.location}' if event.location else ''),
                        'link': f'/agenda/{event.pk}/',
                    }
                )
                count += 1

        print(f'[notify_event_reminder] {count} lembretes enviados.', flush=True)
