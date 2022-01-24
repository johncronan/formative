from django import template
from django.conf import settings
import os

from ..utils import thumbnail_path

register = template.Library()

@register.simple_tag
def file_thumbnail(file):
    path = thumbnail_path(file.path)
    if os.path.isfile(path): return thumbnail_path(file.url)
    return None

@register.filter
def underscore(obj, name):
    attr = getattr(obj, '_' + name)
    if callable(attr): return attr()
    return attr
