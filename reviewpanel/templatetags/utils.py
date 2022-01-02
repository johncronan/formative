from django import template


register = template.Library()

@register.filter
def underscore(obj, name):
    return getattr(obj, '_' + name)
