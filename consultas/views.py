import datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import render, redirect, get_object_or_404
from django.template.loader import render_to_string
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import (
    ASOForm, AtendimentoForm, ConsultaDocumentoForm,
    ConsultaForm, DoctorForm, RescheduleForm,
)
from .models import ASO, Atendimento, Consulta, ConsultaDocumento, Doctor

# Horários disponíveis: 07:30 até 17:30 em intervalos de 30 min
SLOTS = []
_t = datetime.time(7, 30)
while _t <= datetime.time(17, 30):
    SLOTS.append(_t)
    _dt = datetime.datetime.combine(datetime.date.today(), _t) + datetime.timedelta(minutes=30)
    _t = _dt.time()


def _can_access(user):
    return user.can_see_all or user.can_access_consultas


def _is_admin(user):
    return getattr(user, 'can_see_all', False)


def _can_edit(user, consulta):
    return consulta.created_by == user or _is_admin(user)


# ---------------------------------------------------------------------------
# Agenda principal
# ---------------------------------------------------------------------------

@login_required
def agenda(request):
    if not _can_access(request.user):
        return HttpResponseForbidden()

    date_str = request.GET.get('date')
    try:
        date = datetime.date.fromisoformat(date_str)
    except (TypeError, ValueError):
        date = datetime.date.today()

    doctors = Doctor.objects.filter(active=True)
    consultas = Consulta.objects.filter(date=date).select_related('doctor')

    grid = {}
    for c in consultas:
        grid[f"{c.doctor_id}_{c.time.strftime('%H:%M')}"] = c

    slots_str = [s.strftime('%H:%M') for s in SLOTS]

    return render(request, 'consultas/agenda.html', {
        'doctors':   doctors,
        'slots':     slots_str,
        'grid':      grid,
        'date':      date,
        'today':     datetime.date.today(),
        'prev_date': date - datetime.timedelta(days=1),
        'next_date': date + datetime.timedelta(days=1),
    })


# ---------------------------------------------------------------------------
# Detalhe / prontuário da consulta
# ---------------------------------------------------------------------------

@login_required
def consulta_detail(request, pk):
    if not _can_access(request.user):
        return HttpResponseForbidden()

    consulta = get_object_or_404(Consulta, pk=pk)
    atendimento = getattr(consulta, 'atendimento', None)
    aso = getattr(consulta, 'aso', None)
    documentos = consulta.documentos.select_related('enviado_por').all()
    doc_form = ConsultaDocumentoForm()

    return render(request, 'consultas/detail.html', {
        'consulta':    consulta,
        'atendimento': atendimento,
        'aso':         aso,
        'documentos':  documentos,
        'doc_form':    doc_form,
        'atend_form':  AtendimentoForm(instance=atendimento),
    })


# ---------------------------------------------------------------------------
# Criar / Editar consulta
# ---------------------------------------------------------------------------

@login_required
def consulta_create(request):
    if not _can_access(request.user):
        return HttpResponseForbidden()

    initial = {}
    if request.GET.get('date'):
        initial['date'] = request.GET['date']
    if request.GET.get('time'):
        initial['time'] = request.GET['time']
    if request.GET.get('doctor'):
        initial['doctor'] = request.GET['doctor']

    form = ConsultaForm(request.POST or None, initial=initial)
    if form.is_valid():
        consulta = form.save(commit=False)
        consulta.created_by = request.user
        consulta.save()
        messages.success(request, 'Consulta agendada com sucesso.')
        return redirect(f'/consultas/?date={consulta.date}')

    return render(request, 'consultas/form.html', {'form': form, 'title': 'Nova Consulta'})


@login_required
def consulta_edit(request, pk):
    if not _can_access(request.user):
        return HttpResponseForbidden()

    consulta = get_object_or_404(Consulta, pk=pk)
    if not _can_edit(request.user, consulta):
        return HttpResponseForbidden()

    form = ConsultaForm(request.POST or None, instance=consulta)
    if form.is_valid():
        form.save()
        messages.success(request, 'Consulta atualizada.')
        return redirect(f'/consultas/?date={consulta.date}')

    return render(request, 'consultas/form.html', {
        'form': form, 'consulta': consulta, 'title': 'Editar Consulta',
    })


# ---------------------------------------------------------------------------
# Status (HTMX)
# ---------------------------------------------------------------------------

@login_required
@require_POST
def consulta_status(request, pk):
    if not _can_access(request.user):
        return HttpResponseForbidden()

    consulta = get_object_or_404(Consulta, pk=pk)
    new_status = request.POST.get('status')
    valid = [s[0] for s in Consulta.Status.choices]
    if new_status not in valid:
        return HttpResponse('Status inválido', status=400)

    consulta.status = new_status
    consulta.save(update_fields=['status', 'updated_at'])

    html = render_to_string('consultas/_card.html', {
        'c': consulta,
        'user': request.user,
    }, request=request)
    return HttpResponse(html)


# ---------------------------------------------------------------------------
# Remarcar
# ---------------------------------------------------------------------------

@login_required
def consulta_reschedule(request, pk):
    if not _can_access(request.user):
        return HttpResponseForbidden()

    original = get_object_or_404(Consulta, pk=pk)
    if not _can_edit(request.user, original):
        return HttpResponseForbidden()

    form = RescheduleForm(request.POST or None, initial={
        'doctor': original.doctor_id,
        'date':   original.date,
        'time':   original.time,
    })

    if form.is_valid():
        nova = Consulta.objects.create(
            doctor=form.cleaned_data['doctor'],
            patient_name=original.patient_name,
            patient_cpf=original.patient_cpf,
            patient_phone=original.patient_phone,
            date=form.cleaned_data['date'],
            time=form.cleaned_data['time'],
            duration_minutes=original.duration_minutes,
            notes=form.cleaned_data.get('notes') or original.notes,
            created_by=request.user,
        )
        original.status = Consulta.Status.REMARCADO
        original.rescheduled_to = nova
        original.save(update_fields=['status', 'rescheduled_to', 'updated_at'])
        messages.success(request, 'Consulta remarcada.')
        return redirect(f'/consultas/?date={nova.date}')

    return render(request, 'consultas/reschedule.html', {
        'form': form, 'original': original,
    })


# ---------------------------------------------------------------------------
# Excluir
# ---------------------------------------------------------------------------

@login_required
@require_POST
def consulta_delete(request, pk):
    if not _can_access(request.user):
        return HttpResponseForbidden()

    consulta = get_object_or_404(Consulta, pk=pk)
    if not _can_edit(request.user, consulta):
        return HttpResponseForbidden()
    date = consulta.date
    consulta.delete()
    messages.success(request, 'Consulta excluída.')
    return redirect(f'/consultas/?date={date}')


# ---------------------------------------------------------------------------
# Prontuário (Atendimento clínico)
# ---------------------------------------------------------------------------

@login_required
@require_POST
def prontuario_save(request, pk):
    if not _can_access(request.user):
        return HttpResponseForbidden()

    consulta = get_object_or_404(Consulta, pk=pk)
    atendimento = getattr(consulta, 'atendimento', None)

    form = AtendimentoForm(request.POST, instance=atendimento)
    if form.is_valid():
        obj = form.save(commit=False)
        obj.consulta = consulta
        finalizar = request.POST.get('finalizar') == '1'
        if finalizar and not obj.finalizado:
            obj.finalizado = True
            obj.finalizado_em = timezone.now()
            obj.finalizado_por = request.user
            consulta.status = Consulta.Status.FINALIZADO
            consulta.save(update_fields=['status', 'updated_at'])
        obj.save()
        messages.success(request, 'Prontuário salvo.' if not finalizar else 'Prontuário finalizado.')
    else:
        messages.error(request, 'Erro ao salvar prontuário.')

    return redirect('consultas:consulta_detail', pk=pk)


# ---------------------------------------------------------------------------
# Documentos
# ---------------------------------------------------------------------------

@login_required
@require_POST
def documento_upload(request, pk):
    if not _can_access(request.user):
        return HttpResponseForbidden()

    consulta = get_object_or_404(Consulta, pk=pk)
    form = ConsultaDocumentoForm(request.POST, request.FILES)
    if form.is_valid():
        doc = form.save(commit=False)
        doc.consulta = consulta
        doc.nome_original = request.FILES['arquivo'].name
        doc.enviado_por = request.user
        doc.save()
        messages.success(request, 'Documento enviado.')
    else:
        messages.error(request, 'Erro ao enviar documento.')

    return redirect('consultas:consulta_detail', pk=pk)


@login_required
@require_POST
def documento_delete(request, doc_pk):
    if not _can_access(request.user):
        return HttpResponseForbidden()

    doc = get_object_or_404(ConsultaDocumento, pk=doc_pk)
    consulta_pk = doc.consulta_id
    doc.arquivo.delete(save=False)
    doc.delete()
    messages.success(request, 'Documento removido.')
    return redirect('consultas:consulta_detail', pk=consulta_pk)


# ---------------------------------------------------------------------------
# ASO
# ---------------------------------------------------------------------------

@login_required
def aso_edit(request, pk):
    if not _can_access(request.user):
        return HttpResponseForbidden()

    consulta = get_object_or_404(Consulta, pk=pk)
    aso = getattr(consulta, 'aso', None)

    form = ASOForm(request.POST or None, instance=aso)
    if form.is_valid():
        obj = form.save(commit=False)
        obj.consulta = consulta
        if not aso:
            obj.created_by = request.user
        obj.save()
        messages.success(request, 'ASO salvo.')
        return redirect('consultas:consulta_detail', pk=pk)

    return render(request, 'consultas/aso_form.html', {
        'form': form, 'consulta': consulta, 'aso': aso,
    })


# ---------------------------------------------------------------------------
# Médicos (Admin TI apenas)
# ---------------------------------------------------------------------------

@login_required
def doctor_list(request):
    if not _is_admin(request.user):
        return HttpResponseForbidden()
    doctors = Doctor.objects.all()
    return render(request, 'consultas/doctors/list.html', {'doctors': doctors})


@login_required
def doctor_create(request):
    if not _is_admin(request.user):
        return HttpResponseForbidden()
    form = DoctorForm(request.POST or None)
    if form.is_valid():
        form.save()
        messages.success(request, 'Médico cadastrado.')
        return redirect('consultas:doctor_list')
    return render(request, 'consultas/doctors/form.html', {'form': form, 'title': 'Novo Médico'})


@login_required
def doctor_edit(request, pk):
    if not _is_admin(request.user):
        return HttpResponseForbidden()
    doctor = get_object_or_404(Doctor, pk=pk)
    form = DoctorForm(request.POST or None, instance=doctor)
    if form.is_valid():
        form.save()
        messages.success(request, 'Médico atualizado.')
        return redirect('consultas:doctor_list')
    return render(request, 'consultas/doctors/form.html', {
        'form': form, 'doctor': doctor, 'title': 'Editar Médico',
    })
