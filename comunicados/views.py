from django.contrib import messages
from django.http import HttpResponseForbidden
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from .models import Comunicado
from .forms import ComunicadoForm


def _pode_gerenciar(user):
    return user.role in (user.Role.PRESIDENTE, user.Role.ADMIN_TI)


@login_required
def comunicado_list(request):
    comunicados = Comunicado.objects.filter(is_published=True)
    return render(request, 'comunicados/list.html', {
        'comunicados': comunicados,
        'pode_gerenciar': _pode_gerenciar(request.user),
    })


@login_required
def comunicado_detail(request, pk):
    comunicado = get_object_or_404(Comunicado, pk=pk)
    if not comunicado.is_published and not _pode_gerenciar(request.user):
        return HttpResponseForbidden()
    return render(request, 'comunicados/detail.html', {
        'comunicado': comunicado,
        'pode_gerenciar': _pode_gerenciar(request.user),
    })


@login_required
def comunicado_create(request):
    if not _pode_gerenciar(request.user):
        return HttpResponseForbidden()
    if request.method == 'POST':
        form = ComunicadoForm(request.POST)
        if form.is_valid():
            comunicado = form.save(commit=False)
            comunicado.author = request.user
            if comunicado.is_published and not comunicado.published_at:
                comunicado.published_at = timezone.now()
            comunicado.save()
            form.save_m2m()
            return redirect('comunicados:list')
    else:
        form = ComunicadoForm()
    return render(request, 'comunicados/form.html', {'form': form, 'title': 'Novo Comunicado'})


@login_required
def comunicado_edit(request, pk):
    if not _pode_gerenciar(request.user):
        return HttpResponseForbidden()
    comunicado = get_object_or_404(Comunicado, pk=pk)
    if request.method == 'POST':
        form = ComunicadoForm(request.POST, instance=comunicado)
        if form.is_valid():
            c = form.save(commit=False)
            if c.is_published and not c.published_at:
                c.published_at = timezone.now()
            c.save()
            form.save_m2m()
            return redirect('comunicados:list')
    else:
        form = ComunicadoForm(instance=comunicado)
    return render(request, 'comunicados/form.html', {'form': form, 'title': 'Editar Comunicado'})


@login_required
def comunicado_delete(request, pk):
    if not _pode_gerenciar(request.user):
        return HttpResponseForbidden()
    comunicado = get_object_or_404(Comunicado, pk=pk)
    if request.method == 'POST':
        comunicado.delete()
        return redirect('comunicados:list')
    return render(request, 'comunicados/detail.html', {'comunicado': comunicado})
