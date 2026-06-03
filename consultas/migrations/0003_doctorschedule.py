import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('consultas', '0002_atendimento_consulta_documento_aso'),
    ]

    operations = [
        migrations.CreateModel(
            name='DoctorSchedule',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('weekday', models.SmallIntegerField(
                    choices=[
                        (0, 'Segunda-feira'), (1, 'Terça-feira'), (2, 'Quarta-feira'),
                        (3, 'Quinta-feira'),  (4, 'Sexta-feira'),  (5, 'Sábado'), (6, 'Domingo'),
                    ],
                    verbose_name='Dia da semana',
                )),
                ('start_time',   models.TimeField(verbose_name='Início dos atendimentos')),
                ('end_time',     models.TimeField(verbose_name='Fim dos atendimentos')),
                ('slot_minutes', models.PositiveSmallIntegerField(default=30, verbose_name='Duração de cada atendimento (min)')),
                ('break_start',  models.TimeField(blank=True, null=True, verbose_name='Início do intervalo')),
                ('break_end',    models.TimeField(blank=True, null=True, verbose_name='Fim do intervalo')),
                ('doctor', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='schedules',
                    to='consultas.doctor',
                    verbose_name='Médico',
                )),
            ],
            options={
                'verbose_name': 'Grade de Atendimento',
                'verbose_name_plural': 'Grade de Atendimento',
                'ordering': ['weekday', 'start_time'],
                'unique_together': {('doctor', 'weekday')},
            },
        ),
    ]
