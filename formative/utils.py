from django.apps import apps
from django.db.models import Model, Q
from django.conf import settings
from django.core import mail
from django.template import Context, Template, loader
from django.utils.translation import gettext_lazy as _
from django.contrib import admin
import os, glob
from pathlib import Path
import markdown
from markdown_link_attr_modifier import LinkAttrModifierExtension


def create_model(name, fields, app_label='formative', module='',
                 program=None, meta=None, base_class=Model):
    class Meta:
        pass

    setattr(Meta, 'app_label', app_label)
    if meta is not None:
        for key, value in meta.__dict__.items():
            if key[:2] == '__' or key == 'abstract': continue
            setattr(Meta, key, value)
    setattr(Meta, 'db_table', name)
    
    if not module: module = app_label
    attrs = {'__module__': module, 'Meta': Meta}
    attrs.update(dict(fields))

    # Create the class, which automatically triggers ModelBase processing
    model = type(name, (base_class,), attrs)
    
    if program: model._meta.program_slug = program
    return model

def remove_p(text):
    s = text.strip()
    if s[-3-1:] == '</p>':
        i = s.rindex('<p>')
        return s[i+3:-3-1]
    
    return text

def send_email(template, to, subject, context={}, connection=None):
    new_context = { 'settings': settings }
    new_context.update(context)
    context = Context(new_context)
    
    if type(template) != Template: context = new_context # wtf, Django
    
    sub = ' '.join(subject.render(context).splitlines()).rstrip()
    message = template.render(context)
    
    email = mail.EmailMessage(sub, message, settings.CONTACT_EMAIL, [to],
                              connection=connection)
    return email.send()

def submission_link(s, form, rest=''):
    server = settings.DJANGO_SERVER
    if ':' in server or server.endswith('.local'): proto = 'http'
    else: proto = 'https'
    
    return f'{proto}://{server}/{form.program.slug}/{form.slug}/{s._id}/{rest}'

def get_file_extension(name):
    return Path(name).suffix[1:].lower()

def thumbnail_path(path, ext=None):
    idx = path.rindex('.')
    return path[:idx] + '_tn' + (ext and '.'+ext or path[idx:])

def subtitle_path(path, lang):
    idx = path.rindex('.')
    return path[:idx] + '_s_' + lang + '.vtt'

def delete_file(file):
    if os.path.isfile(file.path): os.remove(file.path)
    
    thumb = thumbnail_path(file.path)
    if os.path.isfile(thumb): os.remove(thumb)
    
    for path in glob.glob(subtitle_path(file.path, '*')):
        os.remove(path)

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


class MarkdownFormatter(markdown.Markdown):
    def __init__(self):
        super().__init__(extensions=[
            LinkAttrModifierExtension(new_tab='external_only')
        ])
    
    def convert(self, text):
        self.reset() # in our context this seems to be always needed
        return super().convert(text)
