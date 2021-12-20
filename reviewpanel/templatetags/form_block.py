from django import template

register = template.Library()

# get the form field corresponding to the given block
@register.simple_tag
def block_field(form, block):
    return form[block.name]

@register.simple_tag
def block_labels(labels, block):
    return labels[block.name]

@register.filter
def get_by_style(labels, style):
    if style in labels: return labels[style]
    return None

@register.simple_tag(takes_context=True)
def include_stock(context, block):
    stock = block.stock
    name = 'apply/stock/' + stock.template_name
    template = context.template.engine.get_template(name)
    
    names = stock.field_names()
    if len(names) > 1:
        fields = [ (n[n[1:].index('_')+1:], context['form'][n]) for n in names ]
    else:
        fields = [ (n, context['form'][n]) for n in names ]
    
    return template.render(context.new({
        'block': block,
        'block_fields': fields
    }))
