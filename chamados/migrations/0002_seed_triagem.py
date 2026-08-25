from django.db import migrations


CATEGORIAS = [
    # nome, icone, prioridade_padrao, sla_horas, ordem
    ('Hardware', '🖥️', 'MEDIA', 24, 1),
    ('Software', '💽', 'MEDIA', 24, 2),
    ('Rede / Internet', '🌐', 'ALTA', 8, 3),
    ('Acesso e Senha', '🔑', 'ALTA', 4, 4),
    ('E-mail', '✉️', 'MEDIA', 8, 5),
    ('Impressora', '🖨️', 'MEDIA', 24, 6),
    ('Sistema / Intranet', '🧩', 'ALTA', 8, 7),
    ('Outro assunto', '❓', 'BAIXA', 48, 8),
]


def seed(apps, schema_editor):
    Categoria = apps.get_model('chamados', 'CategoriaChamado')
    Pergunta = apps.get_model('chamados', 'PerguntaTriagem')
    Opcao = apps.get_model('chamados', 'OpcaoTriagem')

    # Idempotente: se já existe uma pergunta raiz, não semeia de novo.
    if Pergunta.objects.filter(is_raiz=True).exists():
        return

    cat = {}
    for nome, icone, prio, sla, ordem in CATEGORIAS:
        cat[nome], _ = Categoria.objects.get_or_create(
            nome=nome,
            defaults={'icone': icone, 'prioridade_padrao': prio, 'sla_horas': sla, 'ordem': ordem},
        )

    raiz = Pergunta.objects.create(
        texto='Com o que você precisa de ajuda?',
        ajuda='Escolha a opção que mais se aproxima do seu problema.',
        is_raiz=True, ordem=0,
    )
    q_hardware = Pergunta.objects.create(texto='Qual o problema com o equipamento?', ordem=1)
    q_software = Pergunta.objects.create(texto='O que acontece com o programa?', ordem=2)
    q_acesso = Pergunta.objects.create(texto='Sobre qual acesso?', ordem=3)

    # Raiz
    Opcao.objects.create(pergunta=raiz, label='Computador, notebook ou periférico', icone='🖥️', ordem=1, proxima_pergunta=q_hardware)
    Opcao.objects.create(pergunta=raiz, label='Um programa ou aplicativo', icone='💽', ordem=2, proxima_pergunta=q_software)
    Opcao.objects.create(pergunta=raiz, label='Internet ou rede', icone='🌐', ordem=3, categoria=cat['Rede / Internet'])
    Opcao.objects.create(pergunta=raiz, label='Login, senha ou permissão', icone='🔑', ordem=4, proxima_pergunta=q_acesso)
    Opcao.objects.create(pergunta=raiz, label='E-mail', icone='✉️', ordem=5, categoria=cat['E-mail'])
    Opcao.objects.create(pergunta=raiz, label='Impressora', icone='🖨️', ordem=6, categoria=cat['Impressora'])
    Opcao.objects.create(pergunta=raiz, label='Sistema interno / Intranet', icone='🧩', ordem=7, categoria=cat['Sistema / Intranet'])
    Opcao.objects.create(pergunta=raiz, label='Outro assunto', icone='❓', ordem=8, categoria=cat['Outro assunto'])

    # Hardware
    Opcao.objects.create(pergunta=q_hardware, label='Não liga / parou de funcionar', ordem=1, categoria=cat['Hardware'], prioridade='URGENTE')
    Opcao.objects.create(pergunta=q_hardware, label='Está muito lento', ordem=2, categoria=cat['Hardware'], prioridade='MEDIA')
    Opcao.objects.create(pergunta=q_hardware, label='Mouse, teclado ou monitor', ordem=3, categoria=cat['Hardware'], prioridade='BAIXA')
    Opcao.objects.create(pergunta=q_hardware, label='Solicitar novo equipamento', ordem=4, categoria=cat['Hardware'], prioridade='BAIXA')

    # Software
    Opcao.objects.create(pergunta=q_software, label='Não abre ou trava', ordem=1, categoria=cat['Software'], prioridade='ALTA')
    Opcao.objects.create(pergunta=q_software, label='Dá erro ao usar', ordem=2, categoria=cat['Software'], prioridade='MEDIA')
    Opcao.objects.create(pergunta=q_software, label='Preciso instalar um programa', ordem=3, categoria=cat['Software'], prioridade='BAIXA')

    # Acesso
    Opcao.objects.create(pergunta=q_acesso, label='Esqueci minha senha', ordem=1, categoria=cat['Acesso e Senha'], prioridade='ALTA')
    Opcao.objects.create(pergunta=q_acesso, label='Estou bloqueado / sem acesso', ordem=2, categoria=cat['Acesso e Senha'], prioridade='ALTA')
    Opcao.objects.create(pergunta=q_acesso, label='Solicitar novo acesso ou permissão', ordem=3, categoria=cat['Acesso e Senha'], prioridade='MEDIA')


def unseed(apps, schema_editor):
    # Reversão segura: remove apenas o conteúdo semeado, se intocado.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('chamados', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
