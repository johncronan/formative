from django import urls
from django.core.cache import cache
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
import sys, importlib, zoneinfo

from .admin import site
from .utils import get_current_site


class DynamicModelMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.models_version = 0
    
    def __call__(self, request):
        version = cache.get('models_version') or 0
        
        if version > self.models_version or site.submissions_registered is None:
            self.models_version = version
            
            site.register_submission_models()
            ContentType.objects.clear_cache()
            # unlike normal Django, we might have had changes to the admin urls
            urls.clear_url_caches()
            if 'urls' in sys.modules: importlib.reload(sys.modules['urls'])
        
        return self.get_response(request)


class TimezoneMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        site = get_current_site(request)
        if site: timezone.activate(zoneinfo.ZoneInfo(site.time_zone))
        else: timezone.deactivate()
        
        return self.get_response(request)
