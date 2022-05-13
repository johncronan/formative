import os
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = []
    
    def generate_superuser(apps, schema_editor):
        from django.contrib import auth
        
        superuser = auth.get_user_model().objects.create_superuser(
            username=os.environ.get('DJANGO_SU_NAME'),
            email=os.environ.get('DJANGO_SU_EMAIL'),
            password=os.environ.get('DJANGO_SU_PASSWORD')
        )
        superuser.save()

    operations = [
        migrations.RunPython(generate_superuser),
    ]
