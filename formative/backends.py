from django.contrib.auth.backends import ModelBackend

from .utils import get_current_site


class SiteAuthBackend(ModelBackend):
    def authenticate(self, request, username=None, **kwargs):
        site = get_current_site(request)
        name = f'{username}__{site.id}'
        # run both, in all cases, to deter timing attacks
        user1 = super().authenticate(request, username, **kwargs)
        user2 = super().authenticate(request, name, **kwargs)
        
        if user1 and (not user1.site or user1.is_staff): return user1
        if user2 and user2.site == site: return user2
        return None
