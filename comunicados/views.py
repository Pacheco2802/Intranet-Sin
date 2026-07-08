from django.contrib import messages
from django.http import HttpResponseForbidden
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from core.models import CustomUser, Notification
from .models import Comunicado
from .forms import ComunicadoForm


def _destinatarios_comunicado(comunicado):
    """Usuários ativos que devem receber notificação do comunicado."""
    depts = list(comunicado.departments.all())
    users = CustomUser.objects.filter(is_active=True)
    if depts:
        users = users.filter(departments__in=depts).distinct()
    return users


def _notificar_publicacao(comunicado, actor):
    link = f'/comunicados/{comunicado.pk}/'
    for u in _destinatarios_comunicado(comunicado):
        Notification.send(
            u, actor, Notification.Type.COMUNICADO_NOVO,
            f'Novo comunicado: {comunicado.title}',
            'Um novo comunicado foi publicado.', link,
        )


def _pode_gerenciar(user):
    return user.role in (user.Role.PRESIDENTE, user.Role.COORD_GERAL, user.Role.DIRETOR, user.Role.ADMIN_TI) or user.can_post_comunicado


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
    if comunicado.is_published:
        comunicado.read_by.add(request.user)
        Notification.objects.filter(
            user=request.user, is_read=False,
            link__startswith=f'/comunicados/{comunicado.pk}/',
        ).update(is_read=True)
    return render(request, 'comunicados/detail.html', {
        'comunicado': comunicado,
        'pode_gerenciar': _pode_gerenciar(request.user),
    })


def _salvar_comunicado(request, form, comunicado=None):
    """Processa salvar/publicar a partir dos botões do formulário."""
    obj = form.save(commit=False)
    if comunicado is None:
        obj.author = request.user

    ja_publicado = bool(comunicado and comunicado.is_published)

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

    # Notifica só na transição rascunho→publicado (evita duplicar em edição)
    if obj.is_published and not ja_publicado:
        _notificar_publicacao(obj, request.user)
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
