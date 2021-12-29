from django.db.models import Q
from django.db.models.signals import post_save, pre_delete, post_delete
from django.dispatch import receiver
from django.utils.text import capfirst

from .models import Form, FormBlock, CustomBlock, FormLabel
from .stock import EmailWidget


@receiver(post_save, sender=Form)
def form_post_save(sender, instance, created, **kwargs):
    if not created: return

    form = instance
    if form.validation_type == Form.Validation.EMAIL:
        b = FormBlock(form=form, page=0, rank=0, name='email',
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

    # set up default labels for the block
    style = FormLabel.LabelStyle.WIDGET
    if block.type == CustomBlock.InputType.TEXT:
        style = block.form.default_text_label_style
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

def delete_block_labels(form, name):
    labels = FormLabel.objects.filter(form=form)
    labels.filter(Q(path=name) | Q(path__startswith=name+'.')).delete()

@receiver(post_delete, sender=CustomBlock)
def customblock_post_delete(sender, instance, **kwargs):
    delete_block_labels(instance.form, instance.name)

@receiver(post_delete, sender=FormBlock)
def formblock_post_delete(sender, instance, **kwargs):
    delete_block_labels(instance.form, instance.name)
