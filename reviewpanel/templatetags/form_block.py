from django import template

register = template.Library()

# get the form field corresponding to the given block
@register.simple_tag
def block_field(form, block):
    return form[block.name]
