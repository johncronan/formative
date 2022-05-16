import os
from django.db import migrations


class Migration(migrations.Migration):
    def change_user_type(apps, schema_editor, back=False):
        ContentType = apps.get_model('contenttypes', 'ContentType')
        label = 'auth'
        if back: label = 'formative'
        ct = ContentType.objects.filter(app_label=label, model='user').first()
        if ct:
            ct.app_label = 'formative'
            if back: ct.app_label = 'auth'
            ct.save()

    def change_type_back(apps, schema_editor):
        return change_user_type(apps, schema_editor, back=True)

    def generate_superuser(apps, schema_editor):
        User = apps.get_model('formative', 'User')
        
        if not User.objects.filter(is_superuser=True).exists():
            superuser = User.objects.create_superuser(
                username=os.environ.get('DJANGO_SU_NAME'),
                email=os.environ.get('DJANGO_SU_EMAIL'),
                password=os.environ.get('DJANGO_SU_PASSWORD')
            )
            superuser.save()
    
    def nop(apps, schema_editor): pass

    dependencies = [
        ('formative', '0008_site_program_sites'),
    ]

    operations = [
        migrations.RunPython(change_user_type, change_type_back),
        migrations.RunPython(generate_superuser, nop)
    ]
