from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST

from .models import Comunicado
from .forms import ComunicadoForm


def _can_create(user):
    return user.role in ('PRESIDENTE', 'ADMIN_TI')


@login_required
def comunicado_list(request):
    user = request.user
    if user.can_see_all:
        qs = Comunicado.objects.all()
    else:
        from django.db.models import Q
        qs = Comunicado.objects.filter(
            is_published=True
        ).filter(
            Q(departments__isnull=True) | Q(departments=user.department)
        ).distinct()
    return render(request, 'comunicados/list.html', {'comunicados': qs})


@login_required
def comunicado_detail(request, pk):
    comunicado = get_object_or_404(Comunicado, pk=pk)
    if not request.user.can_see_all and not comunicado.is_visible_to(request.user):
        return HttpResponseForbidden()
    return render(request, 'comunicados/detail.html', {'comunicado': comunicado})


@login_required
def comunicado_create(request):
    if not _can_create(request.user):
        return HttpResponseForbidden()
    form = ComunicadoForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        comunicado = form.save(commit=False)
        comunicado.author = request.user
        comunicado.save()
        form.save_m2m()
        if form.cleaned_data.get('publish_now'):
            comunicado.publish()
        messages.success(request, 'Comunicado criado com sucesso.')
        return redirect('comunicados:detail', pk=comunicado.pk)
    return render(request, 'comunicados/form.html', {'form': form, 'title': 'Novo Comunicado'})


@login_required
def comunicado_edit(request, pk):
    if not _can_create(request.user):
        return HttpResponseForbidden()
    comunicado = get_object_or_404(Comunicado, pk=pk)
    form = ComunicadoForm(request.POST or None, instance=comunicado)
    if request.method == 'POST' and form.is_valid():
        form.save()
        if form.cleaned_data.get('publish_now') and not comunicado.is_published:
            comunicado.publish()
        messages.success(request, 'Comunicado atualizado.')
        return redirect('comunicados:detail', pk=comunicado.pk)
    return render(request, 'comunicados/form.html', {'form': form, 'title': 'Editar Comunicado', 'comunicado': comunicado})


@login_required
@require_POST
def comunicado_delete(request, pk):
    if not _can_create(request.user):
        return HttpResponseForbidden()
    comunicado = get_object_or_404(Comunicado, pk=pk)
    comunicado.delete()
    messages.success(request, 'Comunicado removido.')
    return redirect('comunicados:list')
