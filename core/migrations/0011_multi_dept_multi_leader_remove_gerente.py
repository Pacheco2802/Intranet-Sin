from django.conf import settings
from django.db import migrations, models


def migrate_forward(apps, schema_editor):
    CustomUser = apps.get_model('core', 'CustomUser')
    Department = apps.get_model('core', 'Department')

    # Copy FK department → M2M departments
    for user in CustomUser.objects.filter(department__isnull=False):
        user.departments.add(user.department_id)

    # Copy FK leader → M2M leaders
    for dept in Department.objects.filter(leader__isnull=False):
        dept.leaders.add(dept.leader_id)

    # Convert GERENTE → LIDER
    CustomUser.objects.filter(role='GERENTE').update(role='LIDER')


def migrate_backward(apps, schema_editor):
    CustomUser = apps.get_model('core', 'CustomUser')
    Department = apps.get_model('core', 'Department')

    # Restore first department to FK
    for user in CustomUser.objects.prefetch_related('departments'):
        first = user.departments.first()
        if first:
            CustomUser.objects.filter(pk=user.pk).update(department_id=first.pk)

    # Restore first leader to FK
    for dept in Department.objects.prefetch_related('leaders'):
        first = dept.leaders.first()
        if first:
            Department.objects.filter(pk=dept.pk).update(leader_id=first.pk)


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0010_add_diretor_role'),
    ]

    operations = [
        # 1. Add M2M departments on CustomUser
        migrations.AddField(
            model_name='customuser',
            name='departments',
            field=models.ManyToManyField(
                blank=True,
                related_name='users',
                to='core.department',
                verbose_name='Departamentos',
            ),
        ),

        # 2. Add M2M leaders on Department
        migrations.AddField(
            model_name='department',
            name='leaders',
            field=models.ManyToManyField(
                blank=True,
                related_name='led_departments',
                to=settings.AUTH_USER_MODEL,
                verbose_name='Líderes',
            ),
        ),

        # 3. Migrate existing FK data → M2M + convert GERENTE
        migrations.RunPython(migrate_forward, migrate_backward),

        # 4. Update role choices (remove GERENTE)
        migrations.AlterField(
            model_name='customuser',
            name='role',
            field=models.CharField(
                choices=[
                    ('PRESIDENTE', 'Presidente'),
                    ('DIRETOR', 'Diretor'),
                    ('ADMIN_TI', 'Administrador TI'),
                    ('LIDER', 'Líder'),
                    ('COLABORADOR', 'Colaborador'),
                ],
                default='COLABORADOR',
                max_length=20,
                verbose_name='Cargo',
            ),
        ),

        # 5. Remove old FK fields
        migrations.RemoveField(
            model_name='customuser',
            name='department',
        ),
        migrations.RemoveField(
            model_name='department',
            name='leader',
        ),
    ]
