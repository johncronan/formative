from django import urls
from django.core.cache import cache
import sys, importlib

from .admin import site


class DynamicModelMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.models_version = 0
    
    def __call__(self, request):
        version = cache.get('models_version') or 0
        
        if version > self.models_version or site.submissions_registered is None:
            self.models_version = version
            
            site.register_submission_models()
            # unlike normal Django, we might have had changes to the admin urls
            urls.clear_url_caches()
            if 'urls' in sys.modules: importlib.reload(sys.modules['urls'])
        
        return self.get_response(request)
