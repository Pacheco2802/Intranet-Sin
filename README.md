# Intranet SINSAÚDE-SP

Sistema interno de gestão desenvolvido para o Sindicato dos Trabalhadores em Saúde do Estado de São Paulo. Centraliza comunicação entre departamentos, controle de tarefas e atendimento a filiados em uma única plataforma.

## Funcionalidades

- **Comunicados** — publicação e distribuição de avisos por departamento
- **Mensagens** — chat interno entre equipes
- **Kanban** — gestão de tarefas com boards por departamento, sub-tarefas e rastreamento de origem
- **Atendimento** — registro e encaminhamento de atendimentos a filiados, com integração automática ao Kanban
- **Controle de acesso** — perfis por cargo (Presidente, Gerente, Líder, Funcionário, Admin TI)
- **LGPD** — consentimento, exportação e anonimização de dados
- **Logs de auditoria** — rastreamento de ações sensíveis

## Tecnologias

- Python 3.14 + Django 6.0
- Tailwind CSS
- PostgreSQL
- `python-decouple` para configuração via variáveis de ambiente

## Instalação

```bash
git clone <repositório>
cd intranet

python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Linux/macOS

pip install -r requirements.txt
```

Crie um arquivo `.env` na raiz do projeto:

```env
SECRET_KEY=sua-chave-secreta-aqui
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

DB_NAME=intranet
DB_USER=postgres
DB_PASSWORD=sua-senha
DB_HOST=localhost
DB_PORT=5432
```

Aplique as migrations e crie o superusuário:

```bash
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Acesse em `http://127.0.0.1:8000`.

## Estrutura

```
intranet/
├── core/           # Usuários, departamentos, equipes, LGPD, auditoria
├── comunicados/    # Publicação de avisos internos
├── mensagens/      # Chat entre equipes
├── kanban/         # Boards, cards, sub-tarefas e anexos
├── atendimento/    # Atendimento a filiados
└── templates/      # Templates globais
```

## Variáveis de ambiente

| Variável | Descrição | Padrão |
|---|---|---|
| `SECRET_KEY` | Chave secreta do Django | obrigatório |
| `DEBUG` | Modo debug | `False` |
| `ALLOWED_HOSTS` | Hosts permitidos separados por vírgula | `localhost,127.0.0.1` |
| `DB_NAME` | Nome do banco PostgreSQL | `intranet` |
| `DB_USER` | Usuário do banco | `postgres` |
| `DB_PASSWORD` | Senha do banco | obrigatório |
| `DB_HOST` | Host do banco | `localhost` |
| `DB_PORT` | Porta do banco | `5432` |

## Licença

Uso interno — SINSAÚDE-SP.
