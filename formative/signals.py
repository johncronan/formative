from django.db.models import Q, Exists, OuterRef
from django.db.models.signals import pre_save, post_save, \
    pre_delete, post_delete
from django.apps import apps
from django.dispatch import Signal, dispatcher, receiver
from django.utils.text import capfirst

from .models import Form, FormBlock, CustomBlock, CollectionBlock, FormLabel, \
    SubmissionRecord
from .stock import EmailWidget
from .utils import any_name_field


@receiver(pre_delete)
def submission_pre_delete(sender, instance, **kwargs):
    if not hasattr(sender._meta, 'program_slug'): return
    if not hasattr(instance, '_get_form'): return
    
    form = instance._get_form()
    SubmissionRecord.objects.filter(
        program=form.program, form=form.slug,
        submission=instance._id, type=SubmissionRecord.RecordType.SUBMISSION
    ).update(deleted=True)
    
    all_submissions_pre_delete.send(sender, instance=instance)

@receiver(post_save, sender=Form)
def form_post_save(sender, instance, created, raw, **kwargs):
    if raw or not created: return

    form = instance
    if form.validation_type == Form.Validation.EMAIL:
        b = FormBlock(form=form, page=0, name='email',
                      options=EmailWidget.default_options())
        b.save()

@receiver(pre_delete, sender=Form)
def form_pre_delete(sender, instance, **kwargs):
    form = instance

    if form.status != Form.Status.DRAFT:
        form.unpublish()

@receiver(pre_save, sender=CustomBlock)
def customblock_pre_save(sender, instance, raw, **kwargs):
    if raw: return
    
    if instance.pk:
        orig = CustomBlock.objects.get(pk=instance.pk)
        instance._old_name = orig.name

def default_text(text):
    return capfirst(text.replace('_', ' '))

@receiver(post_save, sender=CustomBlock)
def customblock_post_save(sender, instance, created, raw, **kwargs):
    if raw: return

    block, new = instance, created
    if not block.page: return # no autocreated labels for autocreated fields

    # set up default labels for the block
    style = FormLabel.LabelStyle.WIDGET
    if block.type == CustomBlock.InputType.TEXT:
        style = block.form.default_text_label_style()
        if block.num_lines > 1: style = FormLabel.LabelStyle.VERTICAL
    elif block.type == CustomBlock.InputType.CHOICE:
        style = FormLabel.LabelStyle.VERTICAL
    elif block.type == CustomBlock.InputType.NUMERIC:
        style = FormLabel.LabelStyle.HORIZONTAL

    text = default_text(block.name)
    if style != FormLabel.LabelStyle.WIDGET: text += ':' # TODO: i18n
    
    l = None
    if new:
        l = FormLabel(form=block.form, path=block.name, style=style, text=text)
    elif block.name != block._old_name:
        try:
            l = FormLabel.objects.get(form=block.form, path=block._old_name,
                                      style=style)
            l.path = block.name
        except FormLabel.DoesNotExist: pass
    if l: l.save()
    
    if block.type != CustomBlock.InputType.CHOICE: return
    paths = []
    for c in 'choices' in block.options and block.choices() or []:
        text = default_text(c)
        new_path = '.'.join((block.name, c))
        if not new and block.name != block._old_name:
            path = '.'.join((block._old_name, c))
        else: path=new_path
        
        l = None
        if not new:
            try:
                l = FormLabel.objects.get(form=block.form, path=path,
                                          style=FormLabel.LabelStyle.WIDGET)
                l.path = new_path
            except FormLabel.DoesNotExist: pass
        
        if not l:
            l = FormLabel(form=block.form, path=new_path,
                          style=FormLabel.LabelStyle.WIDGET, text=text)
        
        l.save()
        paths.append(l.path)
    
    delete_sub_labels(block.form, block.name, paths)
    if not new and block._old_name != block.name:
        delete_sub_labels(block.form, block._old_name)

@receiver(pre_save, sender=FormBlock)
def formblock_pre_save(sender, instance, raw, **kwargs):
    if raw: return
    
    if instance.pk:
        orig = FormBlock.objects.get(pk=instance.pk)
        instance._old_name = orig.name

@receiver(post_save, sender=FormBlock)
def formblock_post_save(sender, instance, created, raw, **kwargs):
    if raw: return
    
    if 'stock' in instance.__dict__: del instance.stock # don't use cache
    block, stock, new = instance, instance.stock, created

    # get stock block's FormLabels and save
    paths = []
    for new_path, (style, text) in stock.widget_labels().items():
        if not new and block.name != block._old_name:
            if '.' in new_path:
                widget = new_path[new_path.index('.')+1:]
                path = '.'.join((block._old_name, widget))
            else: path = block._old_name
        else: path = new_path
        
        l = None
        if not new:
            try:
                l = FormLabel.objects.get(form=block.form, path=path,
                                          style=style)
                l.path = new_path
            except FormLabel.DoesNotExist: pass
        
        if not l:
            l = FormLabel(form=block.form, path=new_path, style=style,
                          text=text)
        l.save()
        paths.append(l.path)
    
    delete_sub_labels(block.form, block.name, paths)
    if not new and block._old_name != block.name:
        delete_sub_labels(block.form, block._old_name)

@receiver(pre_save, sender=CollectionBlock)
def collectionblock_pre_save(sender, instance, raw, **kwargs):
    if raw: return
    
    if instance.pk:
        orig = CollectionBlock.objects.get(pk=instance.pk)
        instance._old_name = orig.name

@receiver(post_save, sender=CollectionBlock)
def collectionblock_post_save(sender, instance, created, raw, **kwargs):
    block, new = instance, created
    if raw: return
    
    fields = block.collection_fields()
    
    existing = block.form.custom_blocks().filter(name__in=fields, page=0)
    existing_names = existing.values_list('name', flat=True)
    for name in fields:
        if name in existing_names: continue
    
        item_field = CustomBlock.text_create(form=block.form, name=name, page=0)
        item_field.save()
    
    refs = CollectionBlock.objects.filter(any_name_field(_=OuterRef('name')),
                                          form=block.form)
    block.form.custom_blocks().filter(~Exists(refs),
                                      page=0, _rank__gt=1).delete()
    
    text, style = default_text(block.name) + ':', FormLabel.LabelStyle.VERTICAL
    paths, id_name, l = [], f'{block.name}{block.id}', None
    try: l = FormLabel.objects.get(form=block.form, path=id_name+'_')
    except FormLabel.DoesNotExist:
        l, _ = FormLabel.objects.get_or_create(form=block.form, path=block.name,
                                               defaults={'style': style,
                                                         'text': text})
    paths.append(l.path)
    
    if block.fixed: return # no implementation yet for fixed + collection
    style = FormLabel.LabelStyle.WIDGET
    for name in block.collection_fields():
        text = default_text(name)
        path, id_path = '.'.join((block.name, name)), id_name + f'.{name}_'
        try: l = FormLabel.objects.get(form=block.form, path=id_path)
        except FormLabel.DoesNotExist:
            l, _ = FormLabel.objects.get_or_create(form=block.form, path=path,
                                                   defaults={'style': style,
                                                             'text': text})
        paths.append(l.path)
    
    # TODO: field name change: update name of existing label rather than delete
    
    delete_sub_labels(block.form, id_name, paths, True)
    if not new and block._old_name != block.name:
        delete_sub_labels(block.form, f'{block._old_name}{block.id}', True)
    
    labels = block.form.labels
    blocks = block.form.collections(name=block.name).exclude(id=block.pk)
    if not blocks: delete_sub_labels(block.form, block.name, paths)
    else:
        for label in labels.filter(path__startswith=block.name+'.'):
            if label.path in paths: continue
            field = label.path[len(block.name)+1:]
            if not blocks.filter(any_name_field(_=field)): label.delete()
    
    if not new and block._old_name != block.name:
        blocks = block.form.collections(name=block._old_name)
        if not blocks: delete_sub_labels(block.form, block._old_name)
        else:
            for label in labels.filter(path__startswith=block._old_name+'.'):
                if not blocks.filter(any_name_field(_=field)): label.delete()

def delete_sub_labels(form, name, exclude=[], id=False):
    sl = form.labels.filter(path__startswith=name+'.').exclude(path__in=exclude)
    if id: sl = sl.filter(path__endswith='_')
    sl.delete()

def delete_block_labels(form, name):
    form.labels.filter(Q(path=name) | Q(path__startswith=name+'.')).delete()

@receiver(post_delete, sender=CustomBlock)
def customblock_post_delete(sender, instance, **kwargs):
    delete_block_labels(instance.form, instance.name)

@receiver(post_delete, sender=FormBlock)
def formblock_post_delete(sender, instance, **kwargs):
    delete_block_labels(instance.form, instance.name)

@receiver(post_delete, sender=CollectionBlock)
def collectionblock_post_delete(sender, instance, **kwargs):
    block = instance
    
    name_with_id = f'{block.name}{block.id}'
    block.form.labels.filter(Q(path=name_with_id+'_') |
                             Q(path__startswith=name_with_id+'.',
                               path__endswith='_')).delete()
    
    blocks = block.form.collections(name=block.name)
    if not blocks: delete_block_labels(block.form, block.name)
    else:
        for name in block.collection_fields():
            if not blocks.filter(any_name_field(_=name)):
                block.form.labels.filter(path='.'.join((block.name,
                                                        name))).delete()
    
    refs = CollectionBlock.objects.filter(any_name_field(_=OuterRef('name')),
                                          form=block.form)
    block.form.custom_blocks().filter(~Exists(refs),
                                      page=0, _rank__gt=1).delete()


app_cache = {}

def populate_app_cache():
    global app_cache
    apps.check_apps_ready()
    for config in apps.app_configs.values(): app_cache[config.name] = config

    
class FormPluginSignal(Signal):
    def _is_active(self, sender, receiver):
        searchpath = receiver.__module__
        app = None
        while True:
            app = app_cache.get(searchpath)
            if '.' not in searchpath or app: break
            searchpath, _ = searchpath.rsplit('.', 1)
        
        return sender and app and app.name in sender.get_plugins()
    
    def send(self, sender, **kwargs):
        if sender and not isinstance(sender, Form):
            raise ValueError('Signal sender needs to be a form.')
        
        responses = []
        if not self.receivers: return responses
        if self.sender_receivers_cache.get(sender) is dispatcher.NO_RECEIVERS:
            return responses
        
        if not app_cache: populate_app_cache()
        
        for receiver in self._live_receivers(sender):
            if self._is_active(sender, receiver):
                response = receiver(signal=self, sender=sender, **kwargs)
                responses.append((receiver, response))
        return responses


form_published_changed = Signal()

register_program_settings = Signal()

register_user_actions = Signal()

all_submissions_pre_delete = Signal()

all_forms_publish = Signal()

all_forms_unpublish = Signal()

register_form_settings = FormPluginSignal()

form_settings_changed = FormPluginSignal()

submission_review_pre = FormPluginSignal()

submission_review_post = FormPluginSignal()

submission_submit_control = FormPluginSignal()

submission_thanks = FormPluginSignal()

submission_handle_submit = FormPluginSignal()
