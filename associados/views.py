from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.timezone import now

from atendimento.models import Atendimento, _cpf_hash
from atendimento.views import _qs_visivel
from core.middleware import AuditMiddleware
from core.models import AuditLog

from .forms import AssociadoForm, CasoDocumentoForm, CasoForm
from .models import Associado, Caso, CasoDocumento


@login_required
def associado_list(request):
    qs = Associado.objects.annotate(n_casos=Count('casos', distinct=True))
    busca_cpf = request.GET.get('cpf', '').strip()
    busca_nome = request.GET.get('nome', '').strip()

    if busca_cpf:
        h = _cpf_hash(busca_cpf)
        qs = qs.filter(cpf_hash=h) if h else qs.none()
    if busca_nome:
        qs = qs.filter(nome__icontains=busca_nome)

    qs = qs.order_by('nome')
    total = qs.count()
    paginator = Paginator(qs, 25)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    params = request.GET.copy()
    params.pop('page', None)

    return render(request, 'associados/list.html', {
        'associados': page_obj,
        'page_obj': page_obj,
        'total': total,
        'busca_cpf': busca_cpf,
        'busca_nome': busca_nome,
        'base_query': params.urlencode(),
    })


@login_required
def associado_detail(request, pk):
    associado = get_object_or_404(Associado, pk=pk)
    atendimentos = _qs_visivel(request.user).filter(
        Q(associado=associado) | Q(cpf_hash=associado.cpf_hash)
    ).select_related('triagem_publica').order_by('-created_at')
    casos = associado.casos.select_related(
        'departamento_responsavel', 'responsavel'
    ).prefetch_related('documentos')

    AuditLog.log(
        request.user, AuditLog.Action.ASSOCIADO_VIEW,
        resource_type='Associado', resource_id=associado.pk,
        ip=AuditMiddleware.get_client_ip(request),
    )

    return render(request, 'associados/detail.html', {
        'associado': associado,
        'atendimentos': atendimentos,
        'casos': casos,
    })


@login_required
def associado_edit(request, pk):
    associado = get_object_or_404(Associado, pk=pk)
    form = AssociadoForm(request.POST or None, instance=associado)
    if request.method == 'POST' and form.is_valid():
        obj = form.save(commit=False)
        obj.atualizado_por = request.user
        obj.save()
        AuditLog.log(
            request.user, AuditLog.Action.ASSOCIADO_EDIT,
            resource_type='Associado', resource_id=obj.pk,
            ip=AuditMiddleware.get_client_ip(request),
        )
        messages.success(request, 'Ficha atualizada.')
        return redirect('associados:detail', pk=obj.pk)
    return render(request, 'associados/form.html', {
        'form': form,
        'associado': associado,
    })


@login_required
def caso_create(request, pk):
    associado = get_object_or_404(Associado, pk=pk)
    form = CasoForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        caso = form.save(commit=False)
        caso.associado = associado
        caso.created_by = request.user
        caso.save()
        AuditLog.log(
            request.user, AuditLog.Action.CASO_CREATE,
            resource_type='Caso', resource_id=caso.pk,
            ip=AuditMiddleware.get_client_ip(request),
        )
        messages.success(request, 'Caso aberto.')
        return redirect('associados:caso_detail', pk=caso.pk)
    return render(request, 'associados/caso_form.html', {
        'form': form,
        'associado': associado,
        'caso': None,
    })


@login_required
def caso_detail(request, pk):
    caso = get_object_or_404(
        Caso.objects.select_related('associado', 'departamento_responsavel', 'responsavel'),
        pk=pk,
    )
    doc_form = CasoDocumentoForm()

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'documento':
            doc_form = CasoDocumentoForm(request.POST, request.FILES)
            if doc_form.is_valid():
                arquivo = doc_form.cleaned_data['arquivo']
                CasoDocumento.objects.create(
                    caso=caso,
                    tipo=doc_form.cleaned_data['tipo'],
                    arquivo=arquivo,
                    nome_original=arquivo.name,
                    enviado_por=request.user,
                )
                AuditLog.log(
                    request.user, AuditLog.Action.CASO_UPDATE,
                    resource_type='Caso', resource_id=caso.pk,
                    ip=AuditMiddleware.get_client_ip(request),
                    evento='documento_enviado', arquivo=arquivo.name[:200],
                )
                messages.success(request, 'Documento anexado.')
                return redirect('associados:caso_detail', pk=caso.pk)

        elif action == 'vincular':
            ids = request.POST.getlist('atendimentos')
            permitidos = _qs_visivel(request.user).filter(
                Q(associado=caso.associado) | Q(cpf_hash=caso.associado.cpf_hash),
                pk__in=ids,
            )
            caso.atendimentos.set(permitidos)
            AuditLog.log(
                request.user, AuditLog.Action.CASO_UPDATE,
                resource_type='Caso', resource_id=caso.pk,
                ip=AuditMiddleware.get_client_ip(request),
                evento='atendimentos_vinculados', total=permitidos.count(),
            )
            messages.success(request, 'Atendimentos vinculados ao caso.')
            return redirect('associados:caso_detail', pk=caso.pk)

    documentos = caso.documentos.select_related('enviado_por')
    vinculados = caso.atendimentos.values_list('pk', flat=True)
    atendimentos_do_associado = _qs_visivel(request.user).filter(
        Q(associado=caso.associado) | Q(cpf_hash=caso.associado.cpf_hash)
    ).order_by('-created_at')

    return render(request, 'associados/caso_detail.html', {
        'caso': caso,
        'associado': caso.associado,
        'documentos': documentos,
        'doc_form': doc_form,
        'atendimentos_do_associado': atendimentos_do_associado,
        'vinculados': set(vinculados),
    })


@login_required
def caso_edit(request, pk):
    caso = get_object_or_404(Caso, pk=pk)
    form = CasoForm(request.POST or None, instance=caso)
    if request.method == 'POST' and form.is_valid():
        obj = form.save(commit=False)
        if obj.status in (Caso.Status.ENCERRADO, Caso.Status.ARQUIVADO):
            if not obj.encerrado_em:
                obj.encerrado_em = now()
        else:
            obj.encerrado_em = None
        obj.save()
        AuditLog.log(
            request.user, AuditLog.Action.CASO_UPDATE,
            resource_type='Caso', resource_id=obj.pk,
            ip=AuditMiddleware.get_client_ip(request),
        )
        messages.success(request, 'Caso atualizado.')
        return redirect('associados:caso_detail', pk=obj.pk)
    return render(request, 'associados/caso_form.html', {
        'form': form,
        'associado': caso.associado,
        'caso': caso,
    })
