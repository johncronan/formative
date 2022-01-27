from django.apps import apps
from django.db.models import Model, Q
from django.conf import settings
from django.core.mail import EmailMessage
from django.template import Context, Template, loader
from django.utils.translation import gettext_lazy as _
from django.contrib import admin
import os
from pathlib import Path


def create_model(name, fields, app_label='formative', module='',
                 table_prefix=None, meta=None, base_class=Model):
    class Meta:
        pass

    setattr(Meta, 'app_label', app_label)
    if meta is not None:
        for key, value in meta.__dict__.items():
            if key[:2] == '__' or key == 'abstract': continue
            setattr(Meta, key, value)
    if table_prefix: setattr(Meta, 'db_table', f'{table_prefix}_{name}')
    
    if not module: module = app_label
    attrs = {'__module__': module, 'Meta': Meta}
    attrs.update(dict(fields))

    # Create the class, which automatically triggers ModelBase processing
    model = type(name, (base_class,), attrs)
    return model

def remove_p(text):
    s = text.strip()
    if s[-3-1:] == '</p>':
        i = s.rindex('<p>')
        return s[i+3:-3-1]
    
    return text

def send_email(template, to, subject, context={}):
    new_context = { 'settings': settings }
    new_context.update(context)
    context = Context(new_context)
    
    if type(template) != Template: context = new_context # wtf, Django
    
    sub = ''.join(subject.render(context).splitlines())
    message = template.render(context)
    
    mail = EmailMessage(sub, message, settings.CONTACT_EMAIL, [to])
    mail.send()

def submission_link(s, form, rest=''):
    server = settings.DJANGO_SERVER
    if ':' in server or server.endswith('.local'): proto = 'http'
    else: proto = 'https'
    
    return f'{proto}://{server}/{form.program.slug}/{form.slug}/{s._id}/{rest}'

def get_file_extension(name):
    return Path(name).suffix[1:].lower()

def thumbnail_path(path):
    return path[:path.rindex('.')] + '_tn.jpg'

def delete_file(file):
    if os.path.isfile(file.path): os.remove(file.path)
    thumb = thumbnail_path(file.path)
    if os.path.isfile(thumb): os.remove(thumb)

def human_readable_filesize(size, decimal_places=2):
    for unit in ['bytes', 'kB', 'MB', 'GB', 'TB', 'PB']:
        if size < 1024 or unit == 'PB': break
        size /= 1024
    return f"{size:.{decimal_places}f} {unit}"

def any_name_field(**kwargs):
    Qs = [ Q(**{ namen + (k != '_' and k or ''): v for k, v in kwargs.items() })
           for namen in ('name1', 'name2', 'name3') ]
    return Qs[0] | Qs[1] | Qs[2]

def get_tooltips():
    return {
        'previoustip': _('Previous Page'),
#        'sortabletip': _('Drag to reorder'),
#        'uploadtip': _('Replace File'),
    }
