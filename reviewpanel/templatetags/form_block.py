from django import template

register = template.Library()

# get the form field corresponding to the given block
@register.simple_tag
def block_field(form, block):
    return form[block.name]

@register.simple_tag(takes_context=True)
def include_stock(context, block):
    stock = block.stock
    name = 'apply/stock/' + stock.template_name
    template = context.template.engine.get_template(name)
    
    fields = [ (name[name[1:].index('_')+1:], context['form'][name])
               for name in stock.field_names() ]
    
    return template.render(context.new({
        'block': block,
        'block_fields': fields
    }))
