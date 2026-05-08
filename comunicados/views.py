from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from .models import Comunicado
from .forms import ComunicadoForm


@login_required
def comunicado_list(request):
    comunicados = Comunicado.objects.filter(is_published=True)
    return render(request, 'comunicados/list.html', {'comunicados': comunicados})


@login_required
def comunicado_detail(request, pk):
    comunicado = get_object_or_404(Comunicado, pk=pk)
    return render(request, 'comunicados/detail.html', {'comunicado': comunicado})


@login_required
def comunicado_create(request):
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
    comunicado = get_object_or_404(Comunicado, pk=pk)
    if request.method == 'POST':
        comunicado.delete()
        return redirect('comunicados:list')
    return render(request, 'comunicados/detail.html', {'comunicado': comunicado})
