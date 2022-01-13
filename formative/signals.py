from django.db.models import Q, Exists, OuterRef
from django.db.models.signals import post_save, pre_delete, post_delete
from django.dispatch import receiver
from django.utils.text import capfirst

from .models import Form, FormBlock, CustomBlock, CollectionBlock, FormLabel
from .stock import EmailWidget
from .utils import any_name_field


@receiver(post_save, sender=Form)
def form_post_save(sender, instance, created, **kwargs):
    if not created: return

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


@receiver(post_save, sender=CustomBlock)
def customblock_post_save(sender, instance, created, **kwargs):
    if not created: return

    block = instance
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

    text = capfirst(block.name)
    if style != FormLabel.LabelStyle.WIDGET: text += ':' # TODO: i18n
    
    l = FormLabel(form=block.form, path=block.name, style=style, text=text)
    l.save()
    
    if block.type == CustomBlock.InputType.CHOICE:
        for c in block.choices():
            text = capfirst(c)
            l = FormLabel(form=block.form, path='.'.join((block.name, c)),
                          style=FormLabel.LabelStyle.WIDGET, text=text)
            l.save()

@receiver(post_save, sender=FormBlock)
def formblock_post_save(sender, instance, created, **kwargs):
    if not created: return

    block, stock = instance, instance.stock

    # get stock block's FormLabels and save
    for path, (style, text) in stock.widget_labels().items():
        l = FormLabel(form=block.form, path=path, style=style, text=text)
        l.save()

@receiver(post_save, sender=CollectionBlock)
def collectionblock_post_save(sender, instance, created, **kwargs):
    block = instance
    
    fields = block.collection_fields()
    
    if created:
        existing = block.form.custom_blocks().filter(name__in=fields, page=0)
        existing_names = existing.values_list('name', flat=True)
        for name in fields:
            if name in existing_names: continue
        
            item_field = CustomBlock.text_create(form=block.form, name=name,
                                                 page=0)
            item_field.save()
    
    refs = CollectionBlock.objects.filter(any_name_field(_=OuterRef('name')),
                                          form=block.form)
    block.form.collections().filter(~Exists(refs), page=0, _rank__gt=1).delete()
    
    if not created: return
    
    text, style = capfirst(block.name) + ':', FormLabel.LabelStyle.VERTICAL
    l = FormLabel.objects.get_or_create(form=block.form, path=block.name,
                                        defaults={'style': style, 'text': text})
    
    style = FormLabel.LabelStyle.WIDGET
    for name in block.collection_fields():
        text, path = capfirst(name), '.'.join((block.name, name))
        l = FormLabel.objects.get_or_create(form=block.form, path=path,
                                            defaults={'style': style,
                                                      'text': text})

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
    if not blocks:
        delete_block_labels(block.form, block.name)
        return
    
    for name in block.collection_fields():
        if not blocks.filter(any_name_field(_=name)):
            block.form.labels.filter(path='.'.join((block.name, name))).delete()
