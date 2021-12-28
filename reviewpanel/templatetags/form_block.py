from django import template

register = template.Library()

# get the form field corresponding to the given block
@register.simple_tag
def block_field(form, block):
    return form[block.name]

@register.simple_tag
def block_labels(labels, block):
    if block.name in labels: return labels[block.name]
    return {}

@register.filter
def get_by_style(labels, style):
    if style in labels: return labels[style]
    return None

@register.filter
def get_by_choice(labels, choice):
    if choice in labels: return labels[choice]
    return None

@register.simple_tag(takes_context=True)
def include_stock(context, block, labels):
    stock = block.stock
    name = 'apply/stock/' + stock.template_name
    template = context.template.engine.get_template(name)
    
    names = stock.widget_names()
    fields = [ (n, context['form'][stock.field_name(n)]) for n in names ]
    
    return template.render(context.new({
        'form_block': block,
        'block_fields': fields,
        'labels': labels
    }))
