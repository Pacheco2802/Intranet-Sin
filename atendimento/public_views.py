"""Rotas públicas de triagem — o filiado preenche sozinho, sem login.

Segurança: nenhuma PII é exibida antes do vínculo conferir; mensagens de erro
são genéricas e idênticas (sem enumeração); throttle por IP e por alvo;
honeypot + tempo mínimo de preenchimento; consentimento LGPD registrado.
"""
import time

from django.contrib import messages
from django.core.signing import BadSignature, TimestampSigner
from django.db import transaction
from django.shortcuts import redirect, render
from django.utils.timezone import localdate, now
from django.views.decorators.cache import never_cache

from core.middleware import AuditMiddleware
from core.models import AuditLog, _anonymize_ip

from . import public_throttle as throttle
from .models import Atendimento, AtendimentoEtapa, TriagemPublica, _cpf_hash
from .public_forms import TriagemEntradaForm, TriagemPublicaForm

ERRO_GENERICO = (
    'Não localizamos uma senha ativa com esses dados. Confira o que você digitou '
    'ou procure a recepção.'
)
TEMPO_MINIMO_SEG = 3
LGPD_POLICY_VERSION = '1.0'

_signer = TimestampSigner(salt='triagem-publica')


def _novo_ts():
    return _signer.sign(str(int(time.time())))


def _ts_valido(valor):
    """True se o formulário foi carregado há pelo menos TEMPO_MINIMO_SEG."""
    if not valor:
        return False
    try:
        raw = _signer.unsign(valor, max_age=4 * 3600)
    except BadSignature:
        return False
    try:
        return (time.time() - int(raw)) >= TEMPO_MINIMO_SEG
    except ValueError:
        return False


def _eh_bot(form):
    return bool(form.data.get('website')) or not _ts_valido(form.data.get('ts'))


def _kiosk(request):
    return request.GET.get('kiosk') or request.POST.get('kiosk') or ''


def _ativos_do_dia():
    return Atendimento.objects.filter(created_at__date=localdate()).exclude(
        status__in=[Atendimento.Status.CONCLUIDO, Atendimento.Status.CANCELADO]
    )


def _log_fail(request, **detail):
    AuditLog.log(
        None, AuditLog.Action.TRIAGEM_FAIL,
        resource_type='TriagemPublica',
        ip=AuditMiddleware.get_client_ip(request), **detail,
    )


def _redirect_ok(request, at=None):
    senha = ''
    if at and at.numero_senha:
        senha = f'{at.nextqs_fila}{at.numero_senha}'
    url = f'/triagem/ok/?senha={senha}'
    if _kiosk(request):
        url += '&kiosk=1'
    return redirect(url)


@transaction.atomic
def _salvar_triagem(request, at, form, origem):
    """Grava a TriagemPublica e todos os efeitos colaterais do envio."""
    data = form.cleaned_data
    primeira_vez = not hasattr(at, 'triagem_publica')

    TriagemPublica.objects.update_or_create(
        atendimento=at,
        defaults={
            'motivo': data['motivo'],
            'descricao': data['descricao'],
            'nome_informado': data.get('nome') or '',
            'telefone': data.get('telefone') or '',
            'email': data.get('email') or '',
            'cargo': data.get('cargo') or '',
            'empregador': data.get('empregador') or '',
            'origem': origem,
            'lgpd_consent': True,
            'policy_version': LGPD_POLICY_VERSION,
            'consent_ip': _anonymize_ip(AuditMiddleware.get_client_ip(request)),
        },
    )

    update_fields = ['triagem_preenchida_em', 'updated_at']
    at.triagem_preenchida_em = now()

    # Complementa o atendimento com o que o filiado informou (sem sobrescrever)
    from associados.models import NOME_PLACEHOLDER
    nome = (data.get('nome') or '').strip()
    if nome and (not at.nome_filiado or at.nome_filiado == NOME_PLACEHOLDER):
        at.nome_filiado = nome[:200]
        update_fields.append('nome_filiado')
    if data.get('telefone') and not at.telefone:
        at.telefone = data['telefone']
        update_fields.append('telefone')
    if data.get('email') and not at.email_filiado:
        at.email_filiado = data['email']
        update_fields.append('email_filiado')
    at.save(update_fields=update_fields)

    # Ficha do associado
    if at.cpf_hash:
        from associados.models import Associado
        associado = Associado.upsert_from_atendimento(at, Associado.Origem.TRIAGEM_PUBLICA)
        if associado and not at.associado_id:
            at.associado = associado
            at.save(update_fields=['associado'])

    if primeira_vez:
        AtendimentoEtapa.objects.create(
            atendimento=at,
            tipo=AtendimentoEtapa.Tipo.NOTA,
            autor=None,
            descricao='Triagem preenchida pelo filiado via formulário público (QR/totem).',
        )

    AuditLog.log(
        None, AuditLog.Action.TRIAGEM_SUBMIT,
        resource_type='Atendimento', resource_id=at.pk,
        ip=AuditMiddleware.get_client_ip(request),
        origem=origem, primeira_vez=primeira_vez,
    )


def _origem(request):
    return TriagemPublica.Origem.TOTEM if _kiosk(request) else TriagemPublica.Origem.QR


@never_cache
def triagem_token(request, token):
    """Formulário já vinculado — destino do QR individual do slip."""
    at = _ativos_do_dia().filter(triagem_token=token).order_by('-created_at').first() if token else None
    if at is None:
        return render(request, 'triagem/invalido.html', {'kiosk': _kiosk(request)}, status=404)

    triagem = getattr(at, 'triagem_publica', None)
    initial = {}
    if triagem:
        initial = {
            'motivo': triagem.motivo, 'descricao': triagem.descricao,
            'nome': triagem.nome_informado, 'telefone': triagem.telefone,
            'email': triagem.email, 'cargo': triagem.cargo,
            'empregador': triagem.empregador, 'lgpd_consent': True,
        }

    if request.method == 'POST':
        if throttle.ip_blocked(request):
            return render(request, 'triagem/throttle.html', {'kiosk': _kiosk(request)}, status=429)
        form = TriagemPublicaForm(request.POST)
        if _eh_bot(form):
            _log_fail(request, motivo='bot', rota='token')
            return _redirect_ok(request, at)  # sucesso falso — não educar o bot
        if form.is_valid():
            throttle.record_ip(request)
            _salvar_triagem(request, at, form, _origem(request))
            return _redirect_ok(request, at)
    else:
        form = TriagemPublicaForm(initial=initial)

    form.fields['ts'].initial = _novo_ts()
    return render(request, 'triagem/form.html', {
        'form': form,
        'at': at,
        'senha_display': f'{at.nextqs_fila}{at.numero_senha}' if at.numero_senha else '',
        'ja_preenchida': triagem is not None,
        'kiosk': _kiosk(request),
        'com_identificacao': False,
    })


@never_cache
def triagem_entrada(request):
    """Entrada do totem / fallback: código curto OU senha + CPF, mais a triagem."""
    if request.method == 'POST':
        if throttle.ip_blocked(request):
            return render(request, 'triagem/throttle.html', {'kiosk': _kiosk(request)}, status=429)
        form = TriagemEntradaForm(request.POST)
        if _eh_bot(form):
            _log_fail(request, motivo='bot', rota='entrada')
            return _redirect_ok(request)
        if form.is_valid():
            throttle.record_ip(request)
            data = form.cleaned_data
            hoje = str(localdate())

            if data['modo'] == 'codigo':
                alvo = f'cod:{data["codigo"]}:{hoje}'
                if throttle.alvo_blocked(alvo):
                    return render(request, 'triagem/throttle.html', {'kiosk': _kiosk(request)}, status=429)
                at = _ativos_do_dia().filter(
                    triagem_codigo=data['codigo']
                ).order_by('-created_at').first()
                if at is None:
                    throttle.record_alvo(alvo)
                    _log_fail(request, motivo='codigo_nao_encontrado')
                    form.add_error('codigo', 'Código não encontrado. Confira o papel ou procure a recepção.')
                else:
                    throttle.clear_alvo(alvo)
                    _salvar_triagem(request, at, form, _origem(request))
                    return _redirect_ok(request, at)

            else:  # modo == 'senha' (fallback senha + CPF)
                fila = data['senha_fila']
                numero = data['senha_numero']
                alvo = f'sen:{fila}{numero}:{hoje}'
                if throttle.alvo_blocked(alvo):
                    return render(request, 'triagem/throttle.html', {'kiosk': _kiosk(request)}, status=429)
                at = _ativos_do_dia().filter(
                    nextqs_fila=fila,
                    numero_senha__in={numero, numero.lstrip('0') or '0'},
                ).order_by('-created_at').first()

                h = _cpf_hash(data['cpf'])
                if at is None or (at.cpf_hash and at.cpf_hash != h):
                    throttle.record_alvo(alvo)
                    _log_fail(request, motivo='senha_cpf_invalidos', fila=fila, numero=numero)
                    form.add_error(None, ERRO_GENERICO)
                else:
                    throttle.clear_alvo(alvo)
                    if not at.cpf_hash:
                        # Stub do sync NextQS sem CPF: adota o CPF validado (claim)
                        at.cpf = data['cpf']
                        at.save(update_fields=['cpf', 'cpf_hash', 'updated_at'])
                        AuditLog.log(
                            None, AuditLog.Action.TRIAGEM_SUBMIT,
                            resource_type='Atendimento', resource_id=at.pk,
                            ip=AuditMiddleware.get_client_ip(request),
                            evento='cpf_autodeclarado_publico', fila=fila, numero=numero,
                        )
                    _salvar_triagem(request, at, form, _origem(request))
                    return _redirect_ok(request, at)
    else:
        form = TriagemEntradaForm()

    form.fields['ts'].initial = _novo_ts()
    return render(request, 'triagem/form.html', {
        'form': form,
        'at': None,
        'senha_display': '',
        'ja_preenchida': False,
        'kiosk': _kiosk(request),
        'com_identificacao': True,
    })


@never_cache
def triagem_ok(request):
    senha = request.GET.get('senha', '')[:8]
    return render(request, 'triagem/success.html', {
        'senha': senha,
        'kiosk': _kiosk(request),
    })


def triagem_privacidade(request):
    """Aviso de privacidade do atendimento ao filiado (público)."""
    return render(request, 'triagem/privacidade.html', {'kiosk': _kiosk(request)})
