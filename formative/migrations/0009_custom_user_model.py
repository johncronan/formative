from django.db import migrations


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


class Migration(migrations.Migration):

    dependencies = [
        ('formative', '0008_site_program_sites'),
    ]

    operations = [
        migrations.RunPython(change_user_type, change_type_back)
    ]
