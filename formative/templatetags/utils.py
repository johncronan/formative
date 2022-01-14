from django import template
from django.conf import settings


register = template.Library()

@register.simple_tag
def submission_link(form, s, rest=''):
    server = settings.DJANGO_SERVER
    if ':' in server or server.endswith('.local'): proto = 'http'
    else: proto = 'https'
    
    return f'{proto}://{server}/{form.program.slug}/{form.slug}/{s._id}/{rest}'

@register.filter
def underscore(obj, name):
    attr = getattr(obj, '_' + name)
    if callable(attr): return attr()
    return attr
