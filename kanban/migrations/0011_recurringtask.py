from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('kanban', '0010_subtask_due_date'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='RecurringTask',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=200, verbose_name='Título')),
                ('description', models.TextField(blank=True, verbose_name='Descrição')),
                ('priority', models.CharField(
                    choices=[('LOW', 'Baixa'), ('MEDIUM', 'Média'), ('HIGH', 'Alta'), ('URGENT', 'Urgente')],
                    default='MEDIUM', max_length=10, verbose_name='Prioridade',
                )),
                ('tags', models.CharField(blank=True, max_length=200, verbose_name='Tags')),
                ('frequency', models.CharField(
                    choices=[('diario', 'Diário'), ('semanal', 'Semanal'), ('quinzenal', 'Quinzenal'), ('mensal', 'Mensal')],
                    max_length=15, verbose_name='Frequência',
                )),
                ('day_of_week', models.SmallIntegerField(
                    blank=True, null=True,
                    choices=[(0, 'Segunda-feira'), (1, 'Terça-feira'), (2, 'Quarta-feira'),
                             (3, 'Quinta-feira'), (4, 'Sexta-feira'), (5, 'Sábado'), (6, 'Domingo')],
                    help_text='Usado para frequência semanal e quinzenal', verbose_name='Dia da semana',
                )),
                ('day_of_month', models.SmallIntegerField(
                    blank=True, null=True,
                    help_text='Usado para frequência mensal (1–28)', verbose_name='Dia do mês',
                )),
                ('due_days_ahead', models.SmallIntegerField(
                    default=0, help_text='0 = sem prazo automático', verbose_name='Prazo (dias após criação)',
                )),
                ('active', models.BooleanField(default=True, verbose_name='Ativa')),
                ('last_generated', models.DateField(blank=True, null=True, verbose_name='Última geração')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('assignee', models.ForeignKey(
                    blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name='recurring_tasks', to=settings.AUTH_USER_MODEL, verbose_name='Responsável',
                )),
                ('board', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='recurring_tasks', to='kanban.board', verbose_name='Quadro',
                )),
                ('column', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='recurring_tasks', to='kanban.column', verbose_name='Coluna inicial',
                )),
                ('created_by', models.ForeignKey(
                    null=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name='created_recurring_tasks', to=settings.AUTH_USER_MODEL, verbose_name='Criado por',
                )),
            ],
            options={
                'verbose_name': 'Tarefa Recorrente',
                'verbose_name_plural': 'Tarefas Recorrentes',
                'ordering': ['board', 'title'],
            },
        ),
    ]
