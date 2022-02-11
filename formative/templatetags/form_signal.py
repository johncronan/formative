from django import template
from django.utils.safestring import mark_safe

import importlib


register = template.Library()


@register.simple_tag
def form_signal(form, signame, **kwargs):
    sigmodule, signame = signame.rsplit('.', 1)
    sigmodule = importlib.import_module(sigmodule)
    signal = getattr(sigmodule, signame)
    
    html_result = []
    for _, response in signal.send(form, **kwargs):
        if response: html_result.append(response)
    return mark_safe(''.join(html_result))
