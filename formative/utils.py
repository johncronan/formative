from django.apps import apps
from django.db.models import Model, Q, OuterRef, Max, Count
from django.conf import settings
from django.core import mail
from django.http import HttpResponse
from django.template import Context, Template, loader
from django.utils.translation import gettext_lazy as _
from django.contrib import admin
import os, glob
from pathlib import Path
import pyexcel
import markdown
from markdown_link_attr_modifier import LinkAttrModifierExtension
from urllib.parse import quote


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


class TabularExport:
    def __init__(self, filename, form, queryset, **kwargs):
        self.filename, self.args = filename, kwargs
        self.fields, self.collections = [], {}
        
        names = []
        for name in self.args:
            if not self.args[name]: continue
            if name.startswith('block_'): names.append(name[len('block_'):])
            elif name.startswith('collection_') and self.args[name][0] != 'no':
                cname = name[len('collection_'):]
                self.collections[cname] = [0, []]
                if self.args[name][0] == 'combine':
                    self.collections[cname][0] = -1
        blocks = { 'block_'+b.name: b
                   for b in form.submission_blocks().filter(name__in=names) }
        
        self.items = {}
        if self.collections:
            item_model = form.item_model
            # item_model's _submission rel doesn't recognize original queryset
            qs = form.model.objects.filter(pk__in=queryset) # but this works
            
            sub_items = item_model.objects.filter(_submission__in=qs)
            items_qs = sub_items.filter(_collection__in=self.collections)
            # TODO order should be by block_rank, cf Submission._collections()
            for item in items_qs.order_by('_collection', '_block', '_rank'):
                app = self.items.setdefault(item._submission_id, {})
                app_col = app.setdefault(item._collection, [])
                app_col.append(item)
            
            for c in self.collections:
                if self.collections[c][0] < 0: continue
                lengths = [ len(app[c])
                            for app in self.items.values() if c in app ]
                self.collections[c][0] = lengths and max(lengths) or 0
        
        for name in self.args:
            if name.startswith('block_'):
                if blocks[name].block_type() == 'stock':
                    for n in blocks[name].stock.widget_names():
                        self.fields.append(blocks[name].stock.field_name(n))
                else: self.fields.append(blocks[name].name)
            
            elif name.startswith('cfield_'):
                cname, field = name[len('cfield_'):].split('.')
                if cname not in self.collections: continue
                self.collections[cname][1].append(field)
    
    def header_row(self):
        ret = ['email']
        for name in self.fields:
            if name.startswith('_'): ret.append(name[1:])
            else: ret.append(name)
        
        for collection, (n, fields) in self.collections.items():
            if not n: continue
            cfields = []
            for field in fields:
                if field == '_file': cfields.append(collection + '_file')
                else: cfields.append(collection + '_' + field)
            if n < 0: ret += cfields
            else: ret += cfields * n
        
        return ret
    
    def data_row(self, submission, sub_items):
        row = [submission._email]
        
        for name in self.fields:
            val = getattr(submission, name)
            if val is None: out = ''
            else: out = str(val)
            row.append(out)
        
        def item_val(item, field):
            if field == '_file' and item._file:
                return 'https://' + settings.DJANGO_SERVER + item._file.url
            val = getattr(item, field)
            if val is None: return ''
            return str(val)
        
        for collection, (n, fields) in self.collections.items():
            col_items = sub_items.setdefault(collection, [])
            if n < 0:
                for field in fields:
                    vals = [ item_val(item, field) for item in col_items ]
                    sep = ' ' if field == '_file' else ', '
                    out = sep.join(vals)
                    row.append(out)
            else:
                for item in col_items:
                    for field in fields: row.append(item_val(item, field))
                row.extend([''] * (n-len(col_items)) * len(fields))
                
        return row
    
    def data_rows(self, queryset):
        ret = []
        for submission in queryset:
            sub_items = self.items.setdefault(submission._id, {})
            row = self.data_row(submission, sub_items)
            ret.append(row)
        return ret
    
    def response(self, queryset):
        data = [self.header_row()]
        data += self.data_rows(queryset)
        
        stream = pyexcel.save_as(array=data, dest_file_type='csv')
        response = HttpResponse(stream, content_type='text/csv')
        
        disp = f"attachment; filename*=UTF-8''" + quote(self.filename)
        response['Content-Disposition'] = disp
        return response


def submission_link(s, form, rest=''):
    server = settings.DJANGO_SERVER
    if ':' in server or server.endswith('.local'): proto = 'http'
    else: proto = 'https'
    
    if s._valid > 1 and not rest:
        if s._valid == form.num_pages(): rest = f'page-{form.num_pages()}'
        else: rest = f'page-{s._valid + 1}'
    
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
