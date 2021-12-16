from django import template

register = template.Library()

# get the form field corresponding to the given block
@register.simple_tag
def block_field(form, block):
    return form[block.name]

@register.simple_tag(takes_context=True)
def include_stock(context, block):
    name = 'apply/stock/' + block.stock.template_name
    t = context.template.engine.get_template(name)
    
    return t.render(context.new({
        'block': block
    }))
