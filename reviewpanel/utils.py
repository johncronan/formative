from django.apps import apps
from django.db.models import Model, Q
from django.conf import settings
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from django.contrib import admin
import os


def create_model(name, fields, app_label='reviewpanel', module='',
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

def send_email(instance, template, to, context={}, context_object_name='obj'):
    new_context = { context_object_name: instance, 'settings': settings }
    new_context.update(context)
    context = new_context

    subject_template = template[:template.index('.html')] + '_subject.html'
    subject = ''.join(render_to_string(subject_template, context).splitlines())

    message = render_to_string(template, context)
    mail = EmailMessage(subject, message, settings.CONTACT_EMAIL, [to])
    mail.send()

def delete_file(file):
    if os.path.isfile(file.path): os.remove(file.path)

def any_name_field(**kwargs):
    Qs = [ Q(**{ namen + (k != '_' and k or ''): v for k, v in kwargs.items() })
           for namen in ('name1', 'name2', 'name3') ]
    return Qs[0] | Qs[1] | Qs[2]
