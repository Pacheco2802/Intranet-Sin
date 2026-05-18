from django.db import migrations, models


def populate_column_type(apps, schema_editor):
    Column = apps.get_model('kanban', 'Column')
    for col in Column.objects.all():
        name_lower = col.name.lower()
        if 'andamento' in name_lower:
            col.column_type = 'em_andamento'
        elif 'conclu' in name_lower or 'final' in name_lower or 'revisão' in name_lower or 'revisao' in name_lower:
            col.column_type = 'status_final'
        else:
            col.column_type = 'a_fazer'
        col.save(update_fields=['column_type'])


class Migration(migrations.Migration):

    dependencies = [
        ('kanban', '0005_card_source_atendimento_id'),
    ]

    operations = [
        migrations.AddField(
            model_name='column',
            name='column_type',
            field=models.CharField(
                choices=[('a_fazer', 'A Fazer'), ('em_andamento', 'Em Andamento'), ('status_final', 'Status Final')],
                default='a_fazer',
                max_length=20,
                verbose_name='Tipo',
            ),
        ),
        migrations.AddField(
            model_name='card',
            name='final_status',
            field=models.CharField(
                blank=True,
                choices=[('concluido', 'Concluído'), ('nao_concluido', 'Não concluído'), ('cancelado', 'Cancelado')],
                default='',
                max_length=20,
                verbose_name='Status final',
            ),
        ),
        migrations.AddField(
            model_name='card',
            name='final_notes',
            field=models.TextField(blank=True, verbose_name='Observações de conclusão'),
        ),
        migrations.RunPython(populate_column_type, migrations.RunPython.noop),
    ]
