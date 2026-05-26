from django.contrib import messages
from django.http import HttpResponseForbidden
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from .models import Comunicado
from .forms import ComunicadoForm


def _pode_gerenciar(user):
    return user.role in (user.Role.PRESIDENTE, user.Role.DIRETOR, user.Role.ADMIN_TI)


@login_required
def comunicado_list(request):
    publicados = Comunicado.objects.filter(is_published=True)
    rascunhos = None
    if _pode_gerenciar(request.user):
        rascunhos = Comunicado.objects.filter(is_published=False).order_by('-created_at')
    return render(request, 'comunicados/list.html', {
        'comunicados': publicados,
        'rascunhos': rascunhos,
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


def _salvar_comunicado(request, form, comunicado=None):
    """Processa salvar/publicar a partir dos botões do formulário."""
    obj = form.save(commit=False)
    if comunicado is None:
        obj.author = request.user

    publicar = request.POST.get('publicar') == '1'
    if publicar:
        obj.is_published = True
        if not obj.published_at:
            obj.published_at = timezone.now()
    else:
        obj.is_published = False

    # Limpar imagem se solicitado
    if request.POST.get('remover_imagem') == '1' and obj.cover_image:
        obj.cover_image.delete(save=False)
        obj.cover_image = None

    obj.save()
    form.save_m2m()
    return obj


@login_required
def comunicado_create(request):
    if not _pode_gerenciar(request.user):
        return HttpResponseForbidden()
    if request.method == 'POST':
        form = ComunicadoForm(request.POST, request.FILES)
        if form.is_valid():
            obj = _salvar_comunicado(request, form)
            if obj.is_published:
                messages.success(request, 'Comunicado publicado com sucesso.')
            else:
                messages.info(request, 'Comunicado salvo como rascunho.')
            return redirect('comunicados:detail', pk=obj.pk)
    else:
        form = ComunicadoForm()
    return render(request, 'comunicados/form.html', {'form': form, 'title': 'Novo Comunicado'})


@login_required
def comunicado_edit(request, pk):
    if not _pode_gerenciar(request.user):
        return HttpResponseForbidden()
    comunicado = get_object_or_404(Comunicado, pk=pk)
    if request.method == 'POST':
        form = ComunicadoForm(request.POST, request.FILES, instance=comunicado)
        if form.is_valid():
            obj = _salvar_comunicado(request, form, comunicado=comunicado)
            if obj.is_published:
                messages.success(request, 'Comunicado publicado.')
            else:
                messages.info(request, 'Rascunho salvo.')
            return redirect('comunicados:detail', pk=obj.pk)
    else:
        form = ComunicadoForm(instance=comunicado)
    return render(request, 'comunicados/form.html', {
        'form': form,
        'title': 'Editar Comunicado',
        'comunicado': comunicado,
    })


@login_required
def comunicado_delete(request, pk):
    if not _pode_gerenciar(request.user):
        return HttpResponseForbidden()
    comunicado = get_object_or_404(Comunicado, pk=pk)
    if request.method == 'POST':
        comunicado.delete()
        messages.success(request, 'Comunicado excluído.')
        return redirect('comunicados:list')
    return render(request, 'comunicados/detail.html', {'comunicado': comunicado, 'pode_gerenciar': True})
