from django import template
from django.conf import settings
import os

from ..utils import thumbnail_path, human_readable_filesize

register = template.Library()

@register.simple_tag
def file_thumbnail(file):
    path = thumbnail_path(file.path)
    if os.path.isfile(path): return thumbnail_path(file.url)
    return None

register.filter('human_readable', human_readable_filesize)

@register.filter
def underscore(obj, name):
    attr = getattr(obj, '_' + name)
    if callable(attr): return attr()
    return attr
