from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('kanban', '0002_board_is_auto_board_is_global'),
        ('core', '0004_department_leader_notification'),
    ]

    operations = [
        migrations.CreateModel(
            name='SubTask',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=200, verbose_name='Título')),
                ('is_done', models.BooleanField(default=False, verbose_name='Concluída')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('card', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='subtasks',
                    to='kanban.card',
                    verbose_name='Card',
                )),
                ('assignee', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='assigned_subtasks',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Responsável',
                )),
                ('target_department', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    to='core.department',
                    verbose_name='Área responsável',
                )),
                ('created_by', models.ForeignKey(
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='created_subtasks',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Criado por',
                )),
            ],
            options={
                'verbose_name': 'Sub-tarefa',
                'verbose_name_plural': 'Sub-tarefas',
                'ordering': ['created_at'],
            },
        ),
    ]
