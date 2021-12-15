from django import template

register = template.Library()

# get the form field corresponding to the given block
@register.simple_tag
def block_field(form, block):
    # in this context, the form is always bound
    return form[block.name]
