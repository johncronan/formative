from django.apps import apps
from django.urls import include, path
from django.views.defaults import page_not_found, server_error
from django.http import Http404
from django.contrib.auth.views import LoginView

from formative import admin

import importlib.util


plugin_patterns = []
for app in apps.get_app_configs():
    if hasattr(app, 'FormativePluginMeta'):
        if importlib.util.find_spec(app.name + '.urls'):
            urlmod = importlib.import_module(app.name + '.urls')
            plugin_patterns.append(path('', include((urlmod.urlpatterns,
                                                     app.label))))

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/login/', LoginView.as_view(template_name='admin/login.html',
                                              next_page='/')),
    path('accounts/', include('django.contrib.auth.urls')),
    path('', include((plugin_patterns, 'plugins'))),
    path('', include('formative.urls')),
#    path('404/', page_not_found, {'exception': Http404()}),
#    path('500/', server_error),
]
