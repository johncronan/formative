from django import template
from collections import OrderedDict

from ..models import FormLabel


register = template.Library()

# get the form field corresponding to the given block
@register.simple_tag
def block_field(form, block):
    if block.name in form.fields: return form[block.name]
    return None

@register.simple_tag
def block_labels(labels, block):
    if block.block_type() == 'collection':
        key = f'{block.name}{block.id}_'
        if key in labels: return labels[key]
    
    if block.name in labels: return labels[block.name]
    return {}

@register.simple_tag
def collection_items(items, block):
    if block.pk in items: return items[block.pk]
    return None

@register.simple_tag
def item_extra_action(item, block, new):
    if new: return 0
    if block.has_file and (item._error or not item._file): return 1
    return 0

@register.filter
def get_by_style(labels, style):
    if labels and style in labels: return labels[style]
    return None

@register.filter
def get_by_choice(labels, choice):
    if choice in labels: return labels[choice]
    return None

@register.filter
def closest_label(labels):
    names = ('WIDGET', 'HORIZONTAL', 'VERTICAL')
    styles = [ FormLabel.LabelStyle[n] for n in names ]
    for style in styles:
        label = get_by_style(labels, style)
        if label: return label
    return None

@register.filter
def for_choice_value(labels, value):
    if value in labels: return closest_label(labels[value])
    return None

@register.simple_tag(takes_context=True)
def include_stock(context, block, labels, review=False):
    stock = block.stock
    
    name = review and stock.review_template_name or stock.template_name
    template = context.template.engine.get_template('apply/stock/' + name)
    
    fields = []
    for n in stock.widget_names():
         field_name = stock.field_name(n)
         if field_name not in context['form'].fields: return ''
         fields.append((n, context['form'][field_name]))
    fields_dict = OrderedDict(fields)
    
    return template.render(context.new({
        'form_block': block,
        'block_fields': fields_dict,
        'labels': labels
    }))

@register.simple_tag(takes_context=True)
def include_stock_review(context, block, labels):
    return include_stock(context, block, labels, review=True)
