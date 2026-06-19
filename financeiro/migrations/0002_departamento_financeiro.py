from django.db import migrations


def criar_departamento_financeiro(apps, schema_editor):
    Department = apps.get_model('core', 'Department')
    # Já existe com o slug esperado: nada a fazer.
    if Department.objects.filter(slug='financeiro').exists():
        return
    # Existe um departamento "Financeiro" com outro slug: alinha o slug.
    dept = Department.objects.filter(name__iexact='Financeiro').first()
    if dept:
        dept.slug = 'financeiro'
        dept.save(update_fields=['slug'])
        return
    Department.objects.create(
        name='Financeiro', slug='financeiro', icon='💰', color='#1a6b45',
        description='Equipe responsável por aprovar reembolsos e realizar pagamentos.',
    )


def remover_departamento_financeiro(apps, schema_editor):
    # Não remove o departamento na reversão (pode ter usuários vinculados).
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('financeiro', '0001_initial'),
        ('core', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(criar_departamento_financeiro, remover_departamento_financeiro),
    ]
